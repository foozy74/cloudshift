# Copyright 2026 The Solution
# All Rights Reserved.

import base64
import hashlib
import hmac
import os
from oslo_log import log as logging
import yaml

LOG = logging.getLogger(__name__)

DEFAULT_ITERATIONS = 100000


def hash_password(password, salt=None, iterations=DEFAULT_ITERATIONS):
    """ Hashes a password using PBKDF2-HMAC-SHA256.

    Returns string format: $pbkdf2-sha256$<iterations>$<salt_b64>$<hash_b64>
    """
    if salt is None:
        salt = os.urandom(16)
    elif isinstance(salt, str):
        salt = salt.encode('utf-8')

    derived = hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), salt, iterations)
    salt_b64 = base64.b64encode(salt).decode('utf-8')
    hash_b64 = base64.b64encode(derived).decode('utf-8')
    return f"$pbkdf2-sha256${iterations}${salt_b64}${hash_b64}"


def verify_password(password, stored_hash):
    """ Verifies a plain password against a stored password hash.
    Supports PBKDF2-SHA256, bcrypt (if installed), or plain string in dev.
    """
    if not stored_hash or not password:
        return False

    if stored_hash.startswith('$pbkdf2-sha256$'):
        parts = stored_hash.split('$')
        if len(parts) != 5:
            LOG.error("Malformed pbkdf2 hash format")
            return False
        try:
            iterations = int(parts[2])
            salt = base64.b64decode(parts[3])
            expected_hash = base64.b64decode(parts[4])
        except Exception as e:
            LOG.error("Failed to decode pbkdf2 hash: %s", e)
            return False

        computed = hashlib.pbkdf2_hmac(
            'sha256', password.encode('utf-8'), salt, iterations)
        return hmac.compare_digest(expected_hash, computed)

    if stored_hash.startswith('$2b$') or stored_hash.startswith('$2a$'):
        try:
            import bcrypt
            return bcrypt.checkpw(
                password.encode('utf-8'), stored_hash.encode('utf-8'))
        except ImportError:
            LOG.warning(
                "bcrypt hash encountered but bcrypt module not installed")
            return False
        except Exception as e:
            LOG.error("bcrypt verification error: %s", e)
            return False

    # Plaintext fallback only if explicitly prefixed with $plain$ for test
    if stored_hash.startswith('$plain$'):
        return hmac.compare_digest(stored_hash[7:], password)

    return False


class LocalAuthBackend(object):
    def __init__(self, users_file):
        self.users_file = users_file

    def _load_users(self):
        if not self.users_file or not os.path.exists(self.users_file):
            LOG.warning("Local users file not found: %s", self.users_file)
            return {}

        try:
            with open(self.users_file, 'r') as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                return {}
            return data.get('users', {})
        except Exception as e:
            LOG.error("Failed to read local users file %s: %s",
                      self.users_file, e)
            return {}

    def authenticate(self, username, password):
        """ Authenticates user credentials against local users file.

        :return: dict with user info, or None
        """
        users = self._load_users()
        user_info = users.get(username)
        if not user_info:
            return None

        if not user_info.get('enabled', True):
            LOG.warning("Local user '%s' is disabled", username)
            return None

        stored_hash = user_info.get('password_hash')
        if not stored_hash or not verify_password(password, stored_hash):
            return None

        roles = user_info.get('roles', ['viewer'])
        if isinstance(roles, str):
            roles = [roles]

        return {
            'username': username,
            'name': user_info.get('display_name', username),
            'roles': roles,
            'auth_source': 'local'
        }
