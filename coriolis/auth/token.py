# Copyright 2026 The Solution
# All Rights Reserved.

import base64
import hashlib
import hmac
import json
import time


def _base64url_encode(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    encoded = base64.urlsafe_b64encode(data).decode('utf-8')
    return encoded.rstrip('=')


def _base64url_decode(data):
    padding = len(data) % 4
    if padding:
        data += '=' * (4 - padding)
    return base64.urlsafe_b64decode(data)


def create_token(payload, secret_key, expiration_hours=8):
    """ Creates a signed JWT using HMAC-SHA256 (HS256).

    :param payload: dict of claims (e.g. {'sub': 'username', 'roles': [...]})
    :param secret_key: string or bytes secret key
    :param expiration_hours: expiration time in hours
    :return: JWT token string
    """
    header = {
        "alg": "HS256",
        "typ": "JWT"
    }

    now = int(time.time())
    token_payload = dict(payload)
    token_payload.setdefault("iat", now)
    if expiration_hours:
        token_payload.setdefault("exp", now + int(expiration_hours * 3600))

    header_b64 = _base64url_encode(
        json.dumps(header, separators=(',', ':')).encode('utf-8'))
    payload_b64 = _base64url_encode(
        json.dumps(token_payload, separators=(',', ':')).encode('utf-8'))

    signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    if isinstance(secret_key, str):
        secret_key = secret_key.encode('utf-8')

    signature = hmac.new(secret_key, signing_input, hashlib.sha256).digest()
    signature_b64 = _base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def verify_token(token, secret_key):
    """ Verifies a JWT token signature and expiration.

    :param token: JWT token string
    :param secret_key: string or bytes secret key
    :return: dict payload if valid
    :raises: ValueError on invalid format, expired token, or signature mismatch
    """
    if not token or not isinstance(token, str):
        raise ValueError("Invalid token format")

    parts = token.split('.')
    if len(parts) != 3:
        raise ValueError("Token must have exactly 3 parts")

    header_b64, payload_b64, signature_b64 = parts

    signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    if isinstance(secret_key, str):
        secret_key = secret_key.encode('utf-8')

    expected_sig = hmac.new(secret_key, signing_input, hashlib.sha256).digest()
    try:
        actual_sig = _base64url_decode(signature_b64)
    except Exception as e:
        raise ValueError(f"Invalid signature encoding: {e}")

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("Token signature mismatch")

    try:
        payload_bytes = _base64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode('utf-8'))
    except Exception as e:
        raise ValueError(f"Invalid payload JSON: {e}")

    exp = payload.get("exp")
    if exp is not None:
        now = int(time.time())
        if now > exp:
            raise ValueError("Token has expired")

    return payload
