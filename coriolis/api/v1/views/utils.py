# Copyright 2023 Cloudbase Solutions Srl
# All Rights Reserved.

import itertools


def format_opt(option, keys=None):
    def transform(key, value):
        if keys and key not in keys:
            return
        yield (key, value)

    return dict(itertools.chain.from_iterable(
        transform(k, v) for k, v in option.items()))


REDACTED_VALUE = '***'
SENSITIVE_KEYS = frozenset(['pkey', 'password', 'private_key', 'certificates'])
SENSITIVE_KEY_SUFFIXES = ('_password', '_pkey', '_private_key')


def _is_sensitive_key(key):
    return isinstance(key, str) and (
        key in SENSITIVE_KEYS or key.endswith(SENSITIVE_KEY_SUFFIXES))


def _redact_value(key, value):
    if not value or not _is_sensitive_key(key):
        return redact_sensitive_info(value)
    if isinstance(value, dict):
        return {k: REDACTED_VALUE for k in value}
    return REDACTED_VALUE


def redact_sensitive_info(value):
    """ Returns a copy of the given value with all credentials (private
    keys, passwords, certificates) masked, at any nesting depth.
    """
    if isinstance(value, dict):
        return {k: _redact_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_info(v) for v in value]
    return value
