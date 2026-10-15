import os
from datetime import timedelta


def _db_url():
    url = os.environ.get("DATABASE_URL", "sqlite:///cdegest.db")
    # Railway / Heroku style URLs
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = _db_url()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    APP_NAME = "CDEgest"
    APP_URL = os.environ.get("APP_URL", "http://localhost:5000")
    DEMO_MODE = os.environ.get("DEMO_MODE", "1") == "1"
    # Show clickable accounts on the login page (never in production)
    SHOW_DEMO_ACCOUNTS = os.environ.get("SHOW_DEMO_ACCOUNTS", "0") == "1"
    # Validation NESDA de la présence : 1 = la DG NESDA valide après le représentant de wilaya
    # clé partagée avec fp.cde.dz pour le transfert automatique des inscriptions (vide = API fermée)
    FP_API_KEY = os.environ.get("FP_API_KEY", "")
    NESDA_DG_VALIDATION = os.environ.get("NESDA_DG_VALIDATION", "0") == "1"
    PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", "https://fp.cde.dz")
    DEFAULT_LANG = "ar"
    LANGS = ("ar", "fr", "en")
    TIMEZONE = "Africa/Algiers"

    CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "contact@fp.cde.dz")
    CONTACT_PHONE = os.environ.get("CONTACT_PHONE", "023 50 56 16")

    PERMANENT_SESSION_LIFETIME = timedelta(days=14)
    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.environ.get("APP_URL", "").startswith("https://")
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    WTF_CSRF_TIME_LIMIT = None


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    DEMO_MODE = True
