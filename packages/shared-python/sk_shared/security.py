import hashlib
import hmac as _hmac
import random
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
    to_encode.update({"exp": expire, "token_type": _TOKEN_TYPE_ACCESS})
    return jose.jwt.encode(to_encode, private_key, algorithm="RS256")

def create_refresh_token(data: dict, private_key: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a refresh token. Refresh tokens cannot be used as access tokens."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=30))
    to_encode.update({"exp": expire, "token_type": _TOKEN_TYPE_REFRESH})
    return jose.jwt.encode(to_encode, private_key, algorithm="RS256")

def decode_access_token(token: str, public_key: str) -> Dict[str, Any]:
    """Decode and validate an access token. Rejects refresh tokens."""
    payload = jose.jwt.decode(token, public_key, algorithms=["RS256"])
    token_type = payload.get("token_type")
    # Only enforce if the token carries a type claim (tokens issued before this
    # change may not have it; once all tokens expire, this can be made strict).
    if token_type is not None and token_type != _TOKEN_TYPE_ACCESS:
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
    return str(random.randint(100000, 999999))

def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()

def verify_hmac(payload_bytes: bytes, signature: str, secret: str) -> bool:
    """Canonical HMAC-SHA256 signature verification shared across all services."""
    if not secret or not signature:
        return False
    expected = _hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return _hmac.compare_digest(expected, signature)


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
