import base64
import hashlib
import hmac as _hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jose.jwt
from cryptography.fernet import Fernet
from passlib.context import CryptContext

# Keep bcrypt verification compatibility, but default new hashes to pbkdf2_sha256.
# This avoids environment-specific bcrypt backend failures in local/test setups.
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")

_TOKEN_TYPE_ACCESS = "access"
_TOKEN_TYPE_REFRESH = "refresh"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, private_key: str, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    # Only set token_type to "access" if not already explicitly set (e.g., by admin token creation)
    if "token_type" not in to_encode:
        to_encode["token_type"] = _TOKEN_TYPE_ACCESS
    to_encode.update({"exp": expire})
    return jose.jwt.encode(to_encode, private_key, algorithm="RS256")

def create_refresh_token(data: dict, private_key: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a refresh token. Refresh tokens cannot be used as access tokens."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=30))
    to_encode.update({"exp": expire, "token_type": _TOKEN_TYPE_REFRESH})
    return jose.jwt.encode(to_encode, private_key, algorithm="RS256")

def decode_access_token(token: str, public_key: str) -> Dict[str, Any]:
    """Decode and validate an access token. Rejects refresh tokens. Accepts user and admin tokens."""
    payload = jose.jwt.decode(token, public_key, algorithms=["RS256"])
    token_type = payload.get("token_type")
    # Only enforce if the token carries a type claim (tokens issued before this
    # change may not have it; once all tokens expire, this can be made strict).
    # Accept "access" tokens (user tokens), "admin" tokens and short-lived "temp" tokens
    if token_type is not None and token_type not in (_TOKEN_TYPE_ACCESS, "admin", "temp"):
        raise jose.jwt.JWTError("Invalid token type: refresh token presented as access token")
    return payload

def decode_refresh_token(token: str, public_key: str) -> Dict[str, Any]:
    """Decode and validate a refresh token. Rejects access tokens."""
    payload = jose.jwt.decode(token, public_key, algorithms=["RS256"])
    token_type = payload.get("token_type")
    if token_type is not None and token_type != _TOKEN_TYPE_REFRESH:
        raise jose.jwt.JWTError("Invalid token type: access token presented as refresh token")
    return payload

def generate_otp() -> str:
    return str(secrets.randbelow(900000) + 100000)

def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()

def verify_hmac(payload_bytes: bytes, signature: str, secret: str) -> bool:
    """Canonical HMAC-SHA256 signature verification shared across all services."""
    if not secret or not signature:
        return False
    expected = _hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return _hmac.compare_digest(expected, signature)


def create_signed_assertion(claims: Dict[str, Any], secret: str, ttl_seconds: int = 60) -> str:
    """Create a short-lived, tamper-evident assertion for service-to-service identity propagation.

    Used when one internal service (e.g. the API Gateway) needs to assert a fact it
    already verified (an authenticated admin's id/role/permissions) to another internal
    service, without that downstream service being able to be tricked by a caller who
    simply sets the equivalent plaintext headers themselves.

    Format: base64url(json_payload) + "." + hex(HMAC-SHA256(json_payload, secret))
    This mirrors a JWT's structure but is built on the already-canonical `verify_hmac`
    primitive above instead of introducing a JWT/keypair dependency for a purely
    internal, short-lived, symmetric-secret use case.

    `claims` should NOT include "iat"/"exp" — those are set here based on `ttl_seconds`.
    """
    payload = dict(claims)
    now = int(time.time())
    payload["iat"] = now
    payload["exp"] = now + ttl_seconds
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
    signature = _hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def verify_signed_assertion(token: str, secret: str) -> Dict[str, Any]:
    """Verify and decode an assertion created by `create_signed_assertion`.

    Raises ValueError (never trusts the input) if the token is malformed, the
    signature doesn't match, or the assertion has expired. Callers should treat any
    ValueError as "reject the request" (403/401), not attempt to partially trust it.
    """
    if not token or "." not in token:
        raise ValueError("MALFORMED_ASSERTION")

    encoded, signature = token.rsplit(".", 1)
    try:
        padding = "=" * (-len(encoded) % 4)
        payload_bytes = base64.urlsafe_b64decode(encoded + padding)
    except Exception as exc:
        raise ValueError("MALFORMED_ASSERTION") from exc

    if not verify_hmac(payload_bytes, signature, secret):
        raise ValueError("INVALID_ASSERTION_SIGNATURE")

    try:
        payload = json.loads(payload_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("MALFORMED_ASSERTION_PAYLOAD") from exc

    if not isinstance(payload, dict):
        raise ValueError("MALFORMED_ASSERTION_PAYLOAD")

    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("ASSERTION_EXPIRED")

    return payload


class SecretService:
    """Manages encryption of DB fields like MFA secrets."""

    @staticmethod
    def generate_encryption_key() -> bytes:
        """Generate a random AES-256 key for Fernet."""
        return Fernet.generate_key()

    @staticmethod
    def encrypt_secret(secret: bytes, key: bytes) -> bytes:
        f = Fernet(key)
        return f.encrypt(secret)

    @staticmethod
    def decrypt_secret(encrypted: bytes, key: bytes) -> bytes:
        f = Fernet(key)
        return f.decrypt(encrypted)
