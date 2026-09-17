# Copyright 2016 Cloudbase Solutions Srl
# All Rights Reserved.

from oslo_log import log as logging
from oslo_middleware import request_id
from oslo_serialization import jsonutils
import webob

from coriolis.api import wsgi
from coriolis.auth import get_auth_manager
from coriolis import context
from coriolis.i18n import _

LOG = logging.getLogger(__name__)


class CoriolisKeystoneContext(wsgi.Middleware):
    def _get_project_id(self, req):
        if 'X_TENANT_ID' in req.headers:
            # This is the new header since Keystone went to ID/Name
            return req.headers['X_TENANT_ID']
        elif 'X_TENANT' in req.headers:
            # This is for legacy compatibility
            return req.headers['X_TENANT']
        else:
            raise webob.exc.HTTPBadRequest(
                explanation=_("No 'X_TENANT_ID' or 'X_TENANT' passed."))

    def _get_user(self, req):
        user = req.headers.get('X_USER')
        user = req.headers.get('X_USER_ID', user)
        if user is None:
            raise webob.exc.HTTPUnauthorized(
                explanation=_("Neither X_USER_ID nor X_USER found in request"))
        return user

    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        user = self._get_user(req)

        project_id = self._get_project_id(req)

        # get the roles
        roles = [r.strip() for r in req.headers.get('X_ROLE', '').split(',')]

        project_name = req.headers.get('X_TENANT_NAME')
        project_domain_name = req.headers.get('X-Project-Domain-Name')
        user_domain_name = req.headers.get('X-User-Domain-Name')

        req_id = req.environ.get(request_id.ENV_REQUEST_ID)
        # TODO(alexpilotti): Check why it's not str
        if isinstance(req_id, bytes):
            req_id = req_id.decode()

        # Get the auth token
        auth_token = req.headers.get('X_AUTH_TOKEN')

        # Build a context, including the auth_token...
        remote_address = req.remote_addr

        service_catalog = None
        if req.headers.get('X_SERVICE_CATALOG') is not None:
            try:
                catalog_header = req.headers.get('X_SERVICE_CATALOG')
                service_catalog = jsonutils.loads(catalog_header)
            except ValueError:
                raise webob.exc.HTTPInternalServerError(
                    explanation=_('Invalid service catalog json.'))

        ctx = context.RequestContext(user,
                                     project_id,
                                     project_name=project_name,
                                     project_domain_name=project_domain_name,
                                     user_domain_name=user_domain_name,
                                     roles=roles,
                                     auth_token=auth_token,
                                     remote_address=remote_address,
                                     service_catalog=service_catalog,
                                     request_id=req_id)

        req.environ['coriolis.context'] = ctx
        return self.application


class CoriolisNoAuthContext(wsgi.Middleware):
    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        if req.method == 'OPTIONS':
            res = webob.Response()
            res.headers['Access-Control-Allow-Origin'] = '*'
            res.headers['Access-Control-Allow-Methods'] = (
                'GET, POST, PUT, DELETE, OPTIONS')
            res.headers['Access-Control-Allow-Headers'] = (
                'Content-Type, X-Project-Id, X-User-Id, X-Role, X-Auth-Token')
            res.status = 204
            return res

        user = req.headers.get(
            'X_USER_ID', req.headers.get('X_USER', 'admin'))
        project_id = req.headers.get(
            'X_TENANT_ID', req.headers.get('X_TENANT', 'admin'))
        roles = [
            r.strip()
            for r in req.headers.get('X_ROLE', 'admin').split(',')]

        ctx = context.RequestContext(
            user,
            project_id,
            project_name=req.headers.get('X_TENANT_NAME', 'admin'),
            roles=roles,
            is_admin=True)

        req.environ['coriolis.context'] = ctx

        res = req.get_response(self.application)
        res.headers['Access-Control-Allow-Origin'] = '*'
        res.headers['Access-Control-Allow-Methods'] = (
            'GET, POST, PUT, DELETE, OPTIONS')
        res.headers['Access-Control-Allow-Headers'] = (
            'Content-Type, X-Project-Id, X-User-Id, X-Role, X-Auth-Token, Authorization')
        return res


class CoriolisTokenAuthContext(wsgi.Middleware):
    def __init__(self, application):
        super(CoriolisTokenAuthContext, self).__init__(application)
        self.auth_mgr = get_auth_manager()

    def _set_cors_headers(self, res):
        res.headers['Access-Control-Allow-Origin'] = '*'
        res.headers['Access-Control-Allow-Methods'] = (
            'GET, POST, PUT, DELETE, OPTIONS')
        res.headers['Access-Control-Allow-Headers'] = (
            'Content-Type, X-Project-Id, X-User-Id, X-Role, X-Auth-Token, Authorization')
        return res

    def _is_unprotected_path(self, path):
        path_clean = path.rstrip('/')
        return (
            path_clean.endswith('/auth/login') or
            path_clean.endswith('/auth/status') or
            path_clean.endswith('/swagger.json') or
            path_clean.endswith('/swagger.html') or
            path_clean == '/v1' or
            path_clean == ''
        )

    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        if req.method == 'OPTIONS':
            res = webob.Response()
            res.status = 204
            return self._set_cors_headers(res)

        path = req.path_info or ''

        # Check if auth strategy is completely disabled ('none')
        if self.auth_mgr.strategy == 'none':
            ctx = context.RequestContext(
                'admin', 'admin', project_name='admin',
                roles=['admin'], is_admin=True)
            req.environ['coriolis.context'] = ctx
            res = req.get_response(self.application)
            return self._set_cors_headers(res)

        # Allow unauthenticated access to login, status, and swagger docs
        if self._is_unprotected_path(path):
            ctx = context.RequestContext(
                'anonymous', 'admin', project_name='admin',
                roles=['viewer'], is_admin=False)
            req.environ['coriolis.context'] = ctx
            res = req.get_response(self.application)
            return self._set_cors_headers(res)

        # Extract token from Authorization header or X-Auth-Token
        auth_header = req.headers.get('Authorization', '')
        token = None
        if auth_header.startswith('Bearer '):
            token = auth_header[7:].strip()
        elif req.headers.get('X-Auth-Token'):
            token = req.headers.get('X-Auth-Token').strip()

        if not token:
            LOG.warning("Unauthorized request to %s: missing token", path)
            res = webob.Response(status=401, content_type='application/json')
            res.json = {
                "error": {
                    "code": 401,
                    "title": "Unauthorized",
                    "message": "Authentication required. Please provide a Bearer token."
                }
            }
            return self._set_cors_headers(res)

        try:
            payload = self.auth_mgr.verify_token(token)
        except Exception as e:
            LOG.warning("Token verification failed for %s: %s", path, e)
            res = webob.Response(status=401, content_type='application/json')
            res.json = {
                "error": {
                    "code": 401,
                    "title": "Unauthorized",
                    "message": f"Invalid or expired token: {str(e)}"
                }
            }
            return self._set_cors_headers(res)

        user = payload.get('sub', 'unknown')
        roles = payload.get('roles', ['viewer'])
        project_id = payload.get('project_id', 'admin')
        is_admin = 'admin' in roles

        ctx = context.RequestContext(
            user,
            project_id,
            project_name=project_id,
            roles=roles,
            is_admin=is_admin,
            auth_token=token)

        req.environ['coriolis.context'] = ctx

        res = req.get_response(self.application)
        return self._set_cors_headers(res)

