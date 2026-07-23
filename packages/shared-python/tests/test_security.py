from datetime import timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose.jwt import JWTError

from sk_shared.security import (
    SecretService,
    create_access_token,
    create_refresh_token,
    create_signed_assertion,
    decode_access_token,
    decode_refresh_token,
    generate_otp,
    get_password_hash,
    hash_otp,
    verify_hmac,
    verify_password,
    verify_signed_assertion,
)


@pytest.fixture(scope="module")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def test_generate_otp_is_six_digits_and_in_range():
    for _ in range(200):
        otp = generate_otp()
        assert len(otp) == 6
        assert otp.isdigit()
        assert 100000 <= int(otp) <= 999999


def test_generate_otp_is_not_deterministic():
    otps = {generate_otp() for _ in range(50)}
    # Extremely unlikely to collide 50/50 times if truly random.
    assert len(otps) > 1


def test_hash_otp_is_deterministic_sha256():
    assert hash_otp("123456") == hash_otp("123456")
    assert hash_otp("123456") != hash_otp("654321")


def test_password_hash_roundtrip():
    hashed = get_password_hash("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_verify_hmac_accepts_valid_signature_and_rejects_tampering():
    secret = "webhook-secret"
    body = b'{"amount": 100}'
    import hashlib
    import hmac as _hmac

    signature = _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_hmac(body, signature, secret) is True
    assert verify_hmac(b'{"amount": 999}', signature, secret) is False
    assert verify_hmac(body, signature, "wrong-secret") is False


def test_verify_hmac_rejects_missing_secret_or_signature():
    assert verify_hmac(b"data", "sig", "") is False
    assert verify_hmac(b"data", "", "secret") is False


def test_access_token_roundtrip(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    token = create_access_token({"user_id": 42}, private_pem, timedelta(minutes=5))
    payload = decode_access_token(token, public_pem)
    assert payload["user_id"] == 42
    assert payload["token_type"] == "access"


def test_refresh_token_rejected_by_decode_access_token(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    refresh_token = create_refresh_token({"user_id": 42}, private_pem)
    with pytest.raises(JWTError):
        decode_access_token(refresh_token, public_pem)


def test_access_token_rejected_by_decode_refresh_token(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    access_token = create_access_token({"user_id": 42}, private_pem)
    with pytest.raises(JWTError):
        decode_refresh_token(access_token, public_pem)


def test_admin_and_temp_token_types_accepted_by_decode_access_token(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    admin_token = create_access_token({"admin_id": 1, "token_type": "admin"}, private_pem)
    temp_token = create_access_token({"user_id": 1, "token_type": "temp"}, private_pem)
    assert decode_access_token(admin_token, public_pem)["token_type"] == "admin"
    assert decode_access_token(temp_token, public_pem)["token_type"] == "temp"


def test_signed_assertion_roundtrip_preserves_claims():
    token = create_signed_assertion(
        {"admin_id": 7, "role": "operations_manager", "permissions": ["admin:notifications:read"]},
        secret="shared-secret",
    )
    claims = verify_signed_assertion(token, "shared-secret")
    assert claims["admin_id"] == 7
    assert claims["role"] == "operations_manager"
    assert claims["permissions"] == ["admin:notifications:read"]
    assert "exp" in claims and "iat" in claims


def test_signed_assertion_rejects_wrong_secret():
    token = create_signed_assertion({"role": "operations_manager"}, secret="right-secret")
    with pytest.raises(ValueError):
        verify_signed_assertion(token, "wrong-secret")


def test_signed_assertion_rejects_tampered_payload():
    token = create_signed_assertion({"role": "cs_agent"}, secret="secret")
    encoded, signature = token.rsplit(".", 1)
    # Swap in a forged payload claiming a higher-privileged role, keep the old signature.
    import base64
    import json as _json

    forged_bytes = _json.dumps({"role": "operations_manager", "iat": 0, "exp": 9999999999}).encode()
    forged_encoded = base64.urlsafe_b64encode(forged_bytes).decode().rstrip("=")
    tampered = f"{forged_encoded}.{signature}"
    with pytest.raises(ValueError):
        verify_signed_assertion(tampered, "secret")


def test_signed_assertion_rejects_expired_token():
    token = create_signed_assertion({"role": "operations_manager"}, secret="secret", ttl_seconds=-1)
    with pytest.raises(ValueError):
        verify_signed_assertion(token, "secret")


def test_signed_assertion_rejects_malformed_token():
    with pytest.raises(ValueError):
        verify_signed_assertion("not-a-valid-token", "secret")
    with pytest.raises(ValueError):
        verify_signed_assertion("", "secret")


def test_secret_service_encrypt_decrypt_roundtrip():
    key = SecretService.generate_encryption_key()
    plaintext = b"mfa-secret-value"
    encrypted = SecretService.encrypt_secret(plaintext, key)
    assert encrypted != plaintext
    assert SecretService.decrypt_secret(encrypted, key) == plaintext
