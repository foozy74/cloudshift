# Copyright 2026 The Solution
# All Rights Reserved.

from oslo_log import log as logging
from webob import exc

from coriolis.api import wsgi as api_wsgi
from coriolis.auth import get_auth_manager

LOG = logging.getLogger(__name__)


class AuthController(api_wsgi.Controller):
    def __init__(self):
        super(AuthController, self).__init__()
        self.auth_mgr = get_auth_manager()

    def login(self, req, body=None):
        if not body:
            try:
                body = req.json_body
            except Exception:
                body = {}

        auth_data = body.get('auth', body)
        username = auth_data.get('username')
        password = auth_data.get('password')

        if not username or not password:
            raise exc.HTTPBadRequest(
                explanation="Missing 'username' or 'password' in request body")

        user_info = self.auth_mgr.authenticate(username, password)
        if not user_info:
            LOG.warning("Failed login attempt for user '%s'", username)
            raise exc.HTTPUnauthorized(
                explanation="Invalid username or password")

        routing_args = req.environ.get('wsgiorg.routing_args')
        project_id = 'admin'
        if routing_args and len(routing_args) > 1 and isinstance(routing_args[1], dict):
            project_id = routing_args[1].get('project_id', 'admin')

        token = self.auth_mgr.issue_token(user_info, project_id=project_id)

        LOG.info("User '%s' logged in successfully with roles: %s (source: %s)",
                 username, user_info.get('roles'), user_info.get('auth_source'))

        return {
            "token": token,
            "user": {
                "username": user_info["username"],
                "name": user_info.get("name", user_info["username"]),
                "roles": user_info.get("roles", ["viewer"]),
                "auth_source": user_info.get("auth_source", "local"),
                "project_id": project_id
            }
        }

    def me(self, req):
        context = req.environ.get("coriolis.context")
        username = getattr(context, 'user_id', None) or getattr(context, 'user', None) if context else None
        if not context or not username:
            raise exc.HTTPUnauthorized(explanation="Not authenticated")

        return {
            "user": {
                "username": username,
                "roles": context.roles,
                "project_id": context.project_id,
                "is_admin": context.is_admin
            }
        }

    def status(self, req):
        return {
            "auth": self.auth_mgr.get_status()
        }


def create_resource():
    return api_wsgi.Resource(AuthController())
