import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class KMSProvider:
    """
    Interface for Key Management Service.
    In the interim S08 mock, we use a single symmetric AES-GCM key from env vars.
    This will be swapped out for actual AWS KMS via Boto3 in production.
    """
    def __init__(self):
        # 32 bytes for AES-256
        key_hex = os.getenv("KMS_MOCK_KEY_HEX", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
        self.key = bytes.fromhex(key_hex)
        self.aesgcm = AESGCM(self.key)

    def encrypt(self, plaintext: str) -> bytes:
        if not plaintext:
            return b""
        # Generate a 12-byte random nonce for AES-GCM
        nonce = os.urandom(12)
        ciphertext = self.aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        # Prepend the nonce to the ciphertext for decryption later
        return nonce + ciphertext

    def decrypt(self, encrypted_data: bytes) -> str:
        if not encrypted_data:
            return ""
        # The first 12 bytes are the nonce
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        plaintext = self.aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')
