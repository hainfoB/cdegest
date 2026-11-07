"""NIN : contrôle de format, chiffrement (Fernet), empreinte HMAC pour la recherche, masquage (US-104)."""
import base64
import hashlib
import hmac
import re

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

NIN_LEN = 18


def normalize(raw):
    return re.sub(r"\D", "", str(raw or ""))


def valid(raw):
    n = normalize(raw)
    return len(n) == NIN_LEN


def _secret():
    return (current_app.config.get("NIN_KEY") or current_app.config["SECRET_KEY"]).encode()


def _fernet():
    key = hashlib.sha256(b"nin-enc|" + _secret()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def fingerprint(raw):
    """Empreinte HMAC-SHA256 : sert aux recherches et au contrôle d'unicité, ne révèle pas le NIN."""
    n = normalize(raw)
    if not n:
        return None
    return hmac.new(hashlib.sha256(b"nin-hmac|" + _secret()).digest(), n.encode(), hashlib.sha256).hexdigest()


def encrypt(raw):
    n = normalize(raw)
    return _fernet().encrypt(n.encode()).decode() if n else None


def decrypt(token):
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def mask(n):
    """4 premiers et 2 derniers chiffres (US-104)."""
    n = normalize(n)
    if len(n) < 8:
        return "—"
    return n[:4] + "•" * (len(n) - 6) + n[-2:]
