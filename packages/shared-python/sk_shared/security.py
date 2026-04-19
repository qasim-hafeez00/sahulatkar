import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jose.jwt
from cryptography.fernet import Fernet
from passlib.context import CryptContext

# Keep bcrypt verification compatibility, but default new hashes to pbkdf2_sha256.
# This avoids environment-specific bcrypt backend failures in local/test setups.
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, private_key: str, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jose.jwt.encode(to_encode, private_key, algorithm="RS256")
    return encoded_jwt

def decode_access_token(token: str, public_key: str) -> Dict[str, Any]:
    return jose.jwt.decode(token, public_key, algorithms=["RS256"])

def generate_otp() -> str:
    return str(random.randint(100000, 999999))

def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


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
