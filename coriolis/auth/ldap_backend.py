# Copyright 2026 The Solution
# All Rights Reserved.

import ssl
from oslo_log import log as logging

LOG = logging.getLogger(__name__)

try:
    import ldap3
    HAS_LDAP3 = True
except ImportError:
    HAS_LDAP3 = False


class LdapAuthBackend(object):
    def __init__(self, conf):
        self.conf = conf
        self.enabled = getattr(conf.ldap, 'enabled', False)
        self.url = getattr(conf.ldap, 'url', '')
        self.use_ssl = getattr(conf.ldap, 'use_ssl', True)
        self.ca_cert_file = getattr(conf.ldap, 'ca_cert_file', None)
        self.insecure = getattr(conf.ldap, 'insecure', False)
        self.bind_dn = getattr(conf.ldap, 'bind_dn', None)
        self.bind_password = getattr(conf.ldap, 'bind_password', None)
        self.user_base_dn = getattr(conf.ldap, 'user_base_dn', '')
        self.user_search_filter = getattr(
            conf.ldap, 'user_search_filter',
            '(&(objectClass=user)(sAMAccountName={username}))')
        self.group_base_dn = getattr(conf.ldap, 'group_base_dn', None)
        self.group_attribute = getattr(conf.ldap, 'group_attribute', 'memberOf')
        self.role_mapping = getattr(conf.ldap, 'role_mapping', {}) or {}
        self.default_role = getattr(conf.ldap, 'default_role', 'viewer')

    def is_available(self):
        if not self.enabled:
            return False
        if not HAS_LDAP3:
            LOG.warning(
                "LDAP authentication enabled in config, but 'ldap3' "
                "package is not installed.")
            return False
        return bool(self.url and self.user_base_dn)

    def _get_server(self):
        tls = None
        if self.use_ssl or self.url.startswith('ldaps://'):
            validate = ssl.CERT_NONE if self.insecure else ssl.CERT_REQUIRED
            tls = ldap3.Tls(validate=validate, ca_certs_file=self.ca_cert_file)

        server = ldap3.Server(self.url, use_ssl=self.use_ssl, tls=tls, get_info=ldap3.NONE)
        return server

    def _map_roles(self, user_groups):
        roles = set()
        # Parse role_mapping if given as string/dict
        mapping = {}
        if isinstance(self.role_mapping, dict):
            mapping = self.role_mapping
        elif isinstance(self.role_mapping, str):
            for entry in self.role_mapping.split(','):
                if ':' in entry:
                    group, role = entry.split(':', 1)
                    mapping[group.strip()] = role.strip()

        # Check each group
        for group in user_groups:
            group_clean = str(group).strip()
            # Match full DN or simple CN
            for mapped_group, mapped_role in mapping.items():
                if (mapped_group.lower() == group_clean.lower() or
                        mapped_group.lower() in group_clean.lower()):
                    roles.add(mapped_role)

        if not roles and self.default_role:
            roles.add(self.default_role)

        return list(roles) or ['viewer']

    def authenticate(self, username, password):
        """ Authenticates username and password against LDAPS.

        :return: dict with user info, or None
        """
        if not self.is_available():
            return None

        if not username or not password:
            return None

        server = self._get_server()

        # Step 1: Bind as service account or connect anonymously to find user DN
        search_conn = None
        user_dn = None
        user_attributes = {}
        try:
            if self.bind_dn and self.bind_password:
                search_conn = ldap3.Connection(
                    server,
                    user=self.bind_dn,
                    password=self.bind_password,
                    auto_bind=True,
                    raise_exceptions=True)
            else:
                search_conn = ldap3.Connection(
                    server,
                    auto_bind=True,
                    raise_exceptions=True)

            # Sanitize username for LDAP query filter
            safe_user = ldap3.utils.conv.escape_filter_chars(username)
            search_filter = self.user_search_filter.format(username=safe_user)
            attributes = ['dn', 'cn', 'displayName', 'mail', self.group_attribute]

            search_conn.search(
                search_base=self.user_base_dn,
                search_filter=search_filter,
                search_scope=ldap3.SUBTREE,
                attributes=attributes)

            if not search_conn.entries:
                LOG.info("LDAP user '%s' not found in search", username)
                return None

            entry = search_conn.entries[0]
            user_dn = entry.entry_dn
            user_attributes = entry.entry_attributes_as_dict

        except Exception as e:
            LOG.error("LDAP search failed for user '%s': %s", username, e)
            return None
        finally:
            if search_conn:
                try:
                    search_conn.unbind()
                except Exception:
                    pass

        if not user_dn:
            return None

        # Step 2: Attempt user bind with user DN and supplied password
        user_conn = None
        try:
            user_conn = ldap3.Connection(
                server,
                user=user_dn,
                password=password,
                auto_bind=True,
                raise_exceptions=True)
            LOG.info("LDAP user '%s' authenticated successfully", username)
        except Exception as e:
            LOG.warning("LDAP authentication failed for '%s': %s", username, e)
            return None
        finally:
            if user_conn:
                try:
                    user_conn.unbind()
                except Exception:
                    pass

        # Step 3: Extract groups and map roles
        raw_groups = user_attributes.get(self.group_attribute, [])
        if isinstance(raw_groups, str):
            raw_groups = [raw_groups]

        roles = self._map_roles(raw_groups)
        display_name = user_attributes.get('displayName')
        if isinstance(display_name, list) and display_name:
            display_name = display_name[0]
        elif not display_name:
            display_name = username

        return {
            'username': username,
            'name': str(display_name),
            'roles': roles,
            'auth_source': 'ldap'
        }
