import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from cryptography.fernet import Fernet

from app.config import get_settings

settings = get_settings()
_fernet = Fernet(settings.FIELD_ENCRYPTION_KEY.encode())


# --------------------------------------------------------- field crypto ---
def encrypt_secret(plaintext: str) -> str:
    """Encrypt sensitive fields (provider API keys, webhook secrets) before storing in DB."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()


def mask_secret(plaintext: str, visible: int = 4) -> str:
    if not plaintext:
        return ""
    if len(plaintext) <= visible:
        return "•" * len(plaintext)
    return "•" * (len(plaintext) - visible) + plaintext[-visible:]


# -------------------------------------------------------- password hash ---
def hash_password(password: str) -> str:
    """PBKDF2-HMAC-SHA256, stdlib only (no bcrypt/passlib) so this never risks a native
    build failure on Render's free tier. Format: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>"""
    iterations = 260_000
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    try:
        algo, iterations_s, salt, hex_digest = hashed.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_s)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
        return hmac.compare_digest(digest.hex(), hex_digest)
    except (ValueError, AttributeError):
        return False


# --------------------------------------------------------------- misc -----
def generate_order_number() -> str:
    return f"FF{datetime.now(timezone.utc).strftime('%y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"


def generate_deposit_number() -> str:
    return f"DP{datetime.now(timezone.utc).strftime('%y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"


def generate_referral_code(telegram_id: int) -> str:
    return f"REF{telegram_id}{secrets.token_hex(2).upper()}"


def generate_idempotency_key(*parts: str) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()


def verify_hmac_signature(secret: str, payload_bytes: bytes, provided_signature: str) -> bool:
    """Generic HMAC-SHA256 signature verification (kept for provider adapters that support
    webhooks in the future). Not used by the polling-based flow, but adapters may still
    implement verify_webhook_signature using this helper."""
    if not provided_signature:
        return False
    expected = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    provided = provided_signature.lower().removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)
