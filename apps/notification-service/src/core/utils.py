import hashlib
import hmac

def verify_hmac(payload_bytes: bytes, signature: str, secret: str) -> bool:
    """Generic HMAC-SHA256 signature verification."""
    if not secret or not signature:
        return False
    
    expected_hex = hmac.new(
        secret.encode("utf-8"), 
        payload_bytes, 
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_hex, signature)
