import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is None:
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
        _fernet = Fernet(key)
    return _fernet


def encrypt(value):
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt(value):
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return value
