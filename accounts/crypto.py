import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


@lru_cache(maxsize=1)
def _fernet():
    # Derives a Fernet key from SECRET_KEY rather than needing a second env
    # var - the key itself is never stored in the database, only ciphertext
    # is, per the "process the key separately from the encrypted data" rule.
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt(value):
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value):
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return value
