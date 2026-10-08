"""Tiny i18n layer: JSON dictionaries, language from ?lang= / cookie / user / default."""
import json
from pathlib import Path

from flask import current_app, request
from flask_login import current_user

_DIR = Path(__file__).parent
_CACHE = {}


def _load(lang):
    if lang not in _CACHE:
        _CACHE[lang] = json.loads((_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    return _CACHE[lang]


def get_lang():
    cached = getattr(request, "_cde_lang", None)
    if cached:
        return cached
    langs = current_app.config["LANGS"]
    lang = request.args.get("lang") or request.cookies.get("lang")
    if lang not in langs and getattr(current_user, "is_authenticated", False):
        lang = current_user.lang
    if lang not in langs:
        lang = current_app.config["DEFAULT_LANG"]
    request._cde_lang = lang
    return lang


def t(key, **kw):
    lang = get_lang()
    text = _load(lang).get(key) or _load("fr").get(key) or key
    return text.format(**kw) if kw else text


def text_dir():
    return "rtl" if get_lang() == "ar" else "ltr"
