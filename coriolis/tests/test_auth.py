# Copyright 2026 The Solution
# All Rights Reserved.

import tempfile
import unittest
from unittest import mock
import yaml

from coriolis.auth import token as token_utils
from coriolis.auth import local_backend
from coriolis.auth import ldap_backend


class TokenTestCase(unittest.TestCase):
    def setUp(self):
        super(TokenTestCase, self).setUp()
        self.secret = 'test-secret-key-12345'
        self.payload = {
            'sub': 'testuser',
            'roles': ['operator', 'viewer'],
            'project_id': 'admin'
        }

    def test_create_and_verify_token_success(self):
        tok = token_utils.create_token(self.payload, self.secret, expiration_hours=1)
        self.assertIsInstance(tok, str)
        self.assertEqual(len(tok.split('.')), 3)

        decoded = token_utils.verify_token(tok, self.secret)
        self.assertEqual(decoded['sub'], 'testuser')
        self.assertEqual(decoded['roles'], ['operator', 'viewer'])
        self.assertEqual(decoded['project_id'], 'admin')
        self.assertIn('iat', decoded)
        self.assertIn('exp', decoded)

    def test_verify_token_wrong_secret(self):
        tok = token_utils.create_token(self.payload, self.secret, expiration_hours=1)
        with self.assertRaises(ValueError) as ctx:
            token_utils.verify_token(tok, 'wrong-secret')
        self.assertIn('signature mismatch', str(ctx.exception).lower())

    def test_verify_token_expired(self):
        # Issue a token already expired
        tok = token_utils.create_token(self.payload, self.secret, expiration_hours=-1)
        with self.assertRaises(ValueError) as ctx:
            token_utils.verify_token(tok, self.secret)
        self.assertIn('expired', str(ctx.exception).lower())

    def test_verify_token_tampered_payload(self):
        tok = token_utils.create_token(self.payload, self.secret, expiration_hours=1)
        parts = tok.split('.')
        # Tamper payload
        tampered = f"{parts[0]}.eyJhZG1pbiI6dHJ1ZX0.{parts[2]}"
        with self.assertRaises(ValueError) as ctx:
            token_utils.verify_token(tampered, self.secret)
        self.assertIn('signature mismatch', str(ctx.exception).lower())

    def test_verify_invalid_format(self):
        with self.assertRaises(ValueError):
            token_utils.verify_token("invalid-token-without-dots", self.secret)
        with self.assertRaises(ValueError):
            token_utils.verify_token("", self.secret)


class LocalBackendTestCase(unittest.TestCase):
    def setUp(self):
        super(LocalBackendTestCase, self).setUp()
        self.password = "SecretPassword123!"
        self.pw_hash = local_backend.hash_password(self.password)

    def test_hash_and_verify_password(self):
        self.assertTrue(self.pw_hash.startswith("$pbkdf2-sha256$"))
        self.assertTrue(local_backend.verify_password(self.password, self.pw_hash))
        self.assertFalse(local_backend.verify_password("WrongPassword", self.pw_hash))
        self.assertFalse(local_backend.verify_password("", self.pw_hash))

    def test_local_auth_backend_authenticate(self):
        users_data = {
            'users': {
                'admin': {
                    'display_name': 'Administrator',
                    'password_hash': self.pw_hash,
                    'roles': ['admin'],
                    'enabled': True
                },
                'disabled_user': {
                    'display_name': 'Disabled User',
                    'password_hash': self.pw_hash,
                    'roles': ['viewer'],
                    'enabled': False
                }
            }
        }

        with tempfile.NamedTemporaryFile('w', delete=False) as f:
            yaml.dump(users_data, f)
            temp_path = f.name

        backend = local_backend.LocalAuthBackend(temp_path)

        # Successful auth
        user = backend.authenticate('admin', self.password)
        self.assertIsNotNone(user)
        self.assertEqual(user['username'], 'admin')
        self.assertEqual(user['roles'], ['admin'])
        self.assertEqual(user['auth_source'], 'local')

        # Bad password
        self.assertIsNone(backend.authenticate('admin', 'WrongPass'))

        # Disabled user
        self.assertIsNone(backend.authenticate('disabled_user', self.password))

        # Unknown user
        self.assertIsNone(backend.authenticate('unknown', self.password))


class LdapBackendTestCase(unittest.TestCase):
    def test_role_mapping(self):
        mock_conf = mock.Mock()
        mock_conf.ldap.enabled = True
        mock_conf.ldap.url = 'ldaps://ad.example.com:636'
        mock_conf.ldap.use_ssl = True
        mock_conf.ldap.ca_cert_file = None
        mock_conf.ldap.insecure = False
        mock_conf.ldap.bind_dn = None
        mock_conf.ldap.bind_password = None
        mock_conf.ldap.user_base_dn = 'DC=example,DC=com'
        mock_conf.ldap.user_search_filter = '(&(objectClass=user)(sAMAccountName={username}))'
        mock_conf.ldap.group_base_dn = 'OU=Groups,DC=example,DC=com'
        mock_conf.ldap.group_attribute = 'memberOf'
        mock_conf.ldap.role_mapping = {
            'CN=Admins,OU=Groups,DC=example,DC=com': 'admin',
            'CN=Operators,OU=Groups,DC=example,DC=com': 'operator'
        }
        mock_conf.ldap.default_role = 'viewer'

        backend = ldap_backend.LdapAuthBackend(mock_conf)

        # Match admin group
        roles = backend._map_roles(['CN=Admins,OU=Groups,DC=example,DC=com'])
        self.assertIn('admin', roles)

        # Match operator group
        roles = backend._map_roles(['CN=Operators,OU=Groups,DC=example,DC=com'])
        self.assertIn('operator', roles)

        # Unmatched group falls back to default_role ('viewer')
        roles = backend._map_roles(['CN=OtherUsers,OU=Groups,DC=example,DC=com'])
        self.assertEqual(roles, ['viewer'])


class AuthManagerTestCase(unittest.TestCase):
    def test_manager_token_issuance_and_verification(self):
        mock_conf = mock.Mock()
        mock_conf.auth.auth_strategy = 'local'
        mock_conf.auth.jwt_secret_key = 'test-secret-manager'
        mock_conf.auth.token_expiration_hours = 4
        mock_conf.auth.local_users_file = '/nonexistent/users.yaml'
        mock_conf.ldap.enabled = False

        from coriolis.auth import manager
        auth_mgr = manager.AuthManager(mock_conf)

        user_info = {
            'username': 'admin',
            'name': 'Administrator',
            'roles': ['admin'],
            'auth_source': 'local'
        }

        token = auth_mgr.issue_token(user_info, project_id='admin')
        self.assertIsInstance(token, str)

        payload = auth_mgr.verify_token(token)
        self.assertEqual(payload['sub'], 'admin')
        self.assertEqual(payload['roles'], ['admin'])
        self.assertEqual(payload['project_id'], 'admin')


class AuthControllerTestCase(unittest.TestCase):
    def setUp(self):
        super(AuthControllerTestCase, self).setUp()
        from coriolis.api.v1 import auth as auth_api
        self.controller = auth_api.AuthController()

    def test_login_missing_credentials(self):
        import webob
        from webob import exc
        req = webob.Request.blank('/v1/auth/login', method='POST')
        req.json = {}
        with self.assertRaises(exc.HTTPBadRequest):
            self.controller.login(req)

    def test_login_success(self):
        import webob
        req = webob.Request.blank('/v1/auth/login', method='POST')
        req.json = {'username': 'testuser', 'password': 'testpassword'}

        mock_user = {
            'username': 'testuser',
            'name': 'Test User',
            'roles': ['operator'],
            'auth_source': 'local'
        }

        with mock.patch.object(self.controller.auth_mgr, 'authenticate', return_value=mock_user), \
             mock.patch.object(self.controller.auth_mgr, 'issue_token', return_value='mock.jwt.token'):
            res = self.controller.login(req)
            self.assertEqual(res['token'], 'mock.jwt.token')
            self.assertEqual(res['user']['username'], 'testuser')
            self.assertEqual(res['user']['roles'], ['operator'])

    def test_me_endpoint_authenticated(self):
        import webob
        from coriolis import context
        req = webob.Request.blank('/v1/auth/me', method='GET')
        ctx = context.RequestContext('testuser', 'admin', roles=['admin'], is_admin=True)
        req.environ['coriolis.context'] = ctx

        res = self.controller.me(req)
        self.assertEqual(res['user']['username'], 'testuser')
        self.assertTrue(res['user']['is_admin'])


class TokenAuthMiddlewareTestCase(unittest.TestCase):
    def setUp(self):
        super(TokenAuthMiddlewareTestCase, self).setUp()
        from coriolis.api.middleware import auth as auth_middleware

        self.called = False

        def dummy_app(environ, start_response):
            self.called = True
            start_response('200 OK', [('Content-Type', 'application/json')])
            return [b'{"status": "ok"}']

        self.dummy_app = dummy_app
        self.middleware = auth_middleware.CoriolisTokenAuthContext(self.dummy_app)

    def test_options_cors_preflight(self):
        import webob
        req = webob.Request.blank('/v1/admin/transfers', method='OPTIONS')
        res = req.get_response(self.middleware)
        self.assertEqual(res.status_code, 204)
        self.assertEqual(res.headers.get('Access-Control-Allow-Origin'), '*')

    def test_unprotected_path_login(self):
        import webob
        req = webob.Request.blank('/v1/auth/login', method='POST')
        res = req.get_response(self.middleware)
        self.assertTrue(self.called)
        self.assertEqual(res.status_code, 200)

    def test_protected_path_missing_token(self):
        import webob
        req = webob.Request.blank('/v1/admin/transfers', method='GET')
        with mock.patch.object(self.middleware.auth_mgr, 'strategy', 'hybrid'):
            res = req.get_response(self.middleware)
            self.assertEqual(res.status_code, 401)
            self.assertIn('Authentication required', res.text)

    def test_protected_path_valid_token(self):
        import webob
        req = webob.Request.blank('/v1/admin/transfers', method='GET')
        req.headers['Authorization'] = 'Bearer valid-jwt-token'

        mock_payload = {
            'sub': 'validuser',
            'roles': ['admin'],
            'project_id': 'admin'
        }

        with mock.patch.object(self.middleware.auth_mgr, 'strategy', 'hybrid'), \
             mock.patch.object(self.middleware.auth_mgr, 'verify_token', return_value=mock_payload):
            res = req.get_response(self.middleware)
            self.assertEqual(res.status_code, 200)
            self.assertIn('coriolis.context', req.environ)
            ctx = req.environ['coriolis.context']
            self.assertEqual(ctx.user_id, 'validuser')
            self.assertEqual(ctx.roles, ['admin'])
            self.assertTrue(ctx.is_admin)


if __name__ == '__main__':
    unittest.main()

