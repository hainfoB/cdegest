"""Codes à usage unique (ES-11) : 6 chiffres, 5 min, 5 essais, usage unique, haché, 3 envois au plus par 15 min."""
import hashlib
import secrets
from datetime import timedelta

from flask import current_app, request
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..models import Device, OtpCode
from ..utils import utcnow


def issue(user, purpose="login", channel=None):
    cfg = current_app.config
    since = utcnow() - timedelta(minutes=15)
    if OtpCode.query.filter(OtpCode.user_id == user.id, OtpCode.created_at >= since).count() >= cfg["OTP_MAX_SENDS_15MIN"]:
        return None, None
    chans = user.channels()
    if not chans:
        return None, None
    ch = channel if channel in chans else (user.code_channel if user.code_channel in chans else chans[0])
    code = f"{secrets.randbelow(10**6):06d}"
    # un seul code valide à la fois
    for old in OtpCode.query.filter_by(user_id=user.id, purpose=purpose, used_at=None):
        old.used_at = utcnow()
    otp = OtpCode(user_id=user.id, purpose=purpose, channel=ch, code_hash=generate_password_hash(code),
                  expires_at=utcnow() + timedelta(minutes=cfg["OTP_TTL_MIN"]))
    db.session.add(otp)
    db.session.flush()
    from .events import code_sent
    code_sent(user, otp, code)
    return otp, code


def current(user, purpose):
    return (OtpCode.query.filter_by(user_id=user.id, purpose=purpose, used_at=None)
            .order_by(OtpCode.id.desc()).first())


def verify(user, purpose, code):
    """Renvoie 'ok', 'bad', 'expired' ou 'locked'."""
    otp = current(user, purpose)
    if otp is None:
        return "expired"
    if otp.expires_at < utcnow():
        return "expired"
    if otp.attempts >= current_app.config["OTP_MAX_TRIES"]:
        return "locked"
    otp.attempts += 1
    if not check_password_hash(otp.code_hash, (code or "").strip()):
        return "locked" if otp.attempts >= current_app.config["OTP_MAX_TRIES"] else "bad"
    otp.used_at = utcnow()
    if otp.channel == "email":
        user.email_verified_at = user.email_verified_at or utcnow()
    else:
        user.phone_verified_at = user.phone_verified_at or utcnow()
    return "ok"


COOKIE = "cdev"


def _h(tok):
    return hashlib.sha256(("dev|" + tok).encode()).hexdigest()


def known_device(user):
    tok = request.cookies.get(COOKIE)
    if not tok:
        return False
    d = Device.query.filter_by(user_id=user.id, token_hash=_h(tok)).first()
    if d:
        d.last_seen = utcnow()
    return d is not None


def remember_device(user, resp):
    tok = request.cookies.get(COOKIE) or secrets.token_urlsafe(24)
    if not Device.query.filter_by(user_id=user.id, token_hash=_h(tok)).first():
        db.session.add(Device(user_id=user.id, token_hash=_h(tok), label=(request.user_agent.string or "")[:120]))
    resp.set_cookie(COOKIE, tok, max_age=3600 * 24 * 365, httponly=True, samesite="Lax",
                    secure=current_app.config.get("SESSION_COOKIE_SECURE", False))
    return resp
