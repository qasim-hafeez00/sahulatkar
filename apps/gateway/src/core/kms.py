import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.config import settings


class KMSProvider:
    """
    Local AES-256-GCM Key Management mock.

    Production path: when ENVIRONMENT=production and KMS_KEY_ARN is set,
    swap this implementation for AWS Boto3:
        import boto3
        client = boto3.client("kms", region_name="ap-south-1")
        encrypted = client.encrypt(KeyId=settings.KMS_KEY_ARN, Plaintext=plaintext.encode())["CiphertextBlob"]
        plaintext = client.decrypt(CiphertextBlob=ciphertext)["Plaintext"].decode()
    The interface (encrypt/decrypt) is identical, making the swap non-breaking.
    """

    def __init__(self):
        key_hex = settings.KMS_MOCK_KEY_HEX
        self.key = bytes.fromhex(key_hex)
        self.aesgcm = AESGCM(self.key)

    def encrypt(self, plaintext: str) -> bytes:
        if not plaintext:
            return b""
        nonce = os.urandom(12)
        ciphertext = self.aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return nonce + ciphertext

    def decrypt(self, encrypted_data: bytes) -> str:
        if not encrypted_data:
            return ""
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        plaintext = self.aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")

