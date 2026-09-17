# Copyright 2026 The Solution
# All Rights Reserved.

from oslo_config import cfg
from oslo_log import log as logging

from coriolis.auth.ldap_backend import LdapAuthBackend
from coriolis.auth.local_backend import LocalAuthBackend
from coriolis.auth import token as token_utils

LOG = logging.getLogger(__name__)

auth_opts = [
    cfg.StrOpt('auth_strategy', default='hybrid',
               help="Authentication strategy: 'hybrid' (local then ldap), "
                    "'local', 'ldap', or 'none'"),
    cfg.StrOpt('jwt_secret_key', default='coriolis-secret-jwt-key-change-me',
               secret=True,
               help="Secret key used to sign and verify JWT authentication tokens"),
    cfg.IntOpt('token_expiration_hours', default=8,
               help="Expiration time for tokens in hours"),
    cfg.StrOpt('local_users_file', default='/etc/coriolis/users.yaml',
               help="Path to YAML file containing local users and password hashes"),
]

ldap_opts = [
    cfg.BoolOpt('enabled', default=False,
                help="Enable LDAP/LDAPS authentication"),
    cfg.StrOpt('url', default='ldaps://ldap.example.com:636',
               help="LDAP / LDAPS server URL"),
    cfg.BoolOpt('use_ssl', default=True,
                help="Use SSL/TLS for connection"),
    cfg.StrOpt('ca_cert_file', default=None,
               help="Path to CA certificate file for SSL verification"),
    cfg.BoolOpt('insecure', default=False,
               help="Ignore SSL certificate validation errors"),
    cfg.StrOpt('bind_dn', default=None,
               help="Service account DN used for searching"),
    cfg.StrOpt('bind_password', default=None, secret=True,
               help="Password for bind_dn service account"),
    cfg.StrOpt('user_base_dn', default='DC=example,DC=com',
               help="Base DN for searching users"),
    cfg.StrOpt('user_search_filter',
               default='(&(objectClass=user)(sAMAccountName={username}))',
               help="Filter pattern for finding user by username"),
    cfg.StrOpt('group_base_dn', default=None,
               help="Base DN for searching groups"),
    cfg.StrOpt('group_attribute', default='memberOf',
               help="User attribute containing groups (or group attribute)"),
    cfg.DictOpt('role_mapping', default={},
                help="Mapping of LDAP group DN/name to Coriolis role "
                     "(admin, operator, viewer)"),
    cfg.StrOpt('default_role', default='viewer',
               help="Default role assigned if no mapped group matches"),
]

CONF = cfg.CONF


def register_auth_opts(conf):
    conf.register_opts(auth_opts, group='auth')
    conf.register_opts(ldap_opts, group='ldap')


_AUTH_MANAGER = None


class AuthManager(object):
    def __init__(self, conf):
        self.conf = conf
        register_auth_opts(conf)

        self.strategy = getattr(conf.auth, 'auth_strategy', 'hybrid').lower()
        self.jwt_secret = getattr(
            conf.auth, 'jwt_secret_key', 'coriolis-secret-jwt-key-change-me')
        self.expiration_hours = getattr(
            conf.auth, 'token_expiration_hours', 8)
        self.local_users_file = getattr(
            conf.auth, 'local_users_file', '/etc/coriolis/users.yaml')

        self.local_backend = LocalAuthBackend(self.local_users_file)
        self.ldap_backend = LdapAuthBackend(conf)

    def authenticate(self, username, password):
        """ Authenticates a user based on the configured strategy.

        :param username: username string
        :param password: password string
        :return: user_info dict or None
        """
        if self.strategy == 'none':
            return {
                'username': username or 'admin',
                'name': 'Administrator (NoAuth)',
                'roles': ['admin'],
                'auth_source': 'none'
            }

        if self.strategy in ('hybrid', 'local'):
            # Try local backend first
            user_info = self.local_backend.authenticate(username, password)
            if user_info:
                return user_info

        if self.strategy in ('hybrid', 'ldap'):
            # Try LDAP backend
            user_info = self.ldap_backend.authenticate(username, password)
            if user_info:
                return user_info

        return None

    def issue_token(self, user_info, project_id='admin'):
        """ Issues a signed JWT for the authenticated user. """
        payload = {
            'sub': user_info['username'],
            'name': user_info.get('name', user_info['username']),
            'roles': user_info.get('roles', ['viewer']),
            'auth_source': user_info.get('auth_source', 'local'),
            'project_id': project_id,
        }
        return token_utils.create_token(
            payload, self.jwt_secret, self.expiration_hours)

    def verify_token(self, token_str):
        """ Verifies a JWT token and returns the payload dict. """
        return token_utils.verify_token(token_str, self.jwt_secret)

    def get_status(self):
        """ Returns current auth status and configuration for diagnostics. """
        return {
            'strategy': self.strategy,
            'ldap_enabled': self.ldap_backend.is_available(),
            'token_expiration_hours': self.expiration_hours
        }


def get_auth_manager():
    global _AUTH_MANAGER
    if not _AUTH_MANAGER:
        _AUTH_MANAGER = AuthManager(CONF)
    return _AUTH_MANAGER
