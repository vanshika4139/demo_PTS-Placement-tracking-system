"""Field-level encryption for sensitive candidate data (DPDP).

Values are stored as "enc1:<Fernet token>". The key comes from the ENCRYPTION_KEY
environment variable, never from the database. If the key is lost, encrypted data
cannot be recovered, so back it up somewhere safe.
"""
import hashlib
import hmac
import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import String, TypeDecorator

PREFIX = "enc1:"
_fernet = None


def _key():
    key = (os.environ.get("ENCRYPTION_KEY") or "").strip()
    if not key:
        raise RuntimeError("ENCRYPTION_KEY is not set, so sensitive data cannot be encrypted or decrypted.")
    return key


def _get_fernet():
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_key().encode())
    return _fernet


def encrypt_value(value):
    if value is None:
        return None
    text = str(value)
    if text == "":
        return text
    return PREFIX + _get_fernet().encrypt(text.encode("utf-8")).decode("ascii")


def decrypt_value(value):
    """Values that do not start with the prefix are old plain-text rows and are returned as they are."""
    if value is None or not isinstance(value, str) or not value.startswith(PREFIX):
        return value
    try:
        return _get_fernet().decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise RuntimeError("A stored value could not be decrypted. Is ENCRYPTION_KEY the key it was encrypted with?")


def aadhaar_hash(value):
    """One-way fingerprint of an Aadhaar number, only for duplicate checks."""
    if not value:
        return None
    normalized = "".join(str(value).split()).replace("-", "").upper()
    if not normalized:
        return None
    return hmac.new(_key().encode(), ("aadhaar:" + normalized).encode(), hashlib.sha256).hexdigest()


class EncryptedString(TypeDecorator):
    """Encrypts on write and decrypts on read, so the rest of the code is unchanged.
    Note: you cannot filter or search on an encrypted column."""
    impl = String
    cache_ok = True

    def __init__(self, length=500, *args, **kwargs):
        super().__init__(length, *args, **kwargs)

    def process_bind_param(self, value, dialect):
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        return decrypt_value(value)