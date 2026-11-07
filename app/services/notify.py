"""Envoi des messages (EP-11). Prototype : aucun envoi réel, tout est déposé dans la boîte d'envoi simulée.

Règles appliquées : catégories et canaux, heures calmes 21 h – 8 h (RG-47), plafond de 2 messages B ou C
par jour sur le canal mobile (RG-48), un seul message par événement et par canal (RG-50),
rappels désactivables (RG-46), bascule vers l'autre canal en cas d'échec (US-1104).
"""
from datetime import datetime, timedelta

from flask import current_app, url_for

from ..extensions import db
from ..models import Notification
from ..utils import utcnow
from .messages import CATALOG, FOOTER

TZ_OFFSET = timedelta(hours=1)          # Africa/Algiers, sans heure d'été


def local_now():
    return utcnow() + TZ_OFFSET


def _to_utc(local_dt):
    return local_dt - TZ_OFFSET


def mask_email(e):
    if not e or "@" not in e:
        return "—"
    a, d = e.split("@", 1)
    return (a[:1] + "•••@" + d)


def mask_phone(p):
    d = "".join(c for c in (p or "") if c.isdigit())
    return (d[:2] + "•" * max(0, len(d) - 5) + d[-3:]) if len(d) >= 6 else "—"


def recipient(user=None, participant=None, candidature=None):
    """Destinataire normalisé ; un compte est prioritaire sur les coordonnées d'un dossier."""
    src = user or (participant.user if participant is not None and participant.user is not None else None) \
        or (candidature.user if candidature is not None and candidature.user is not None else None)
    if src is not None:
        return {"user": src, "user_id": src.id, "name": src.name.split(" ")[-1] if src.name else "", "email": src.email,
                "phone": src.phone, "whatsapp": src.whatsapp or src.phone, "mobile": src.mobile_channel or "sms",
                "wa_ok": src.wa_consent_at is not None, "lang": src.lang if src.lang in ("ar", "fr") else "fr",
                "reminders": src.reminders}
    o = participant or candidature
    return {"user": None, "user_id": None, "name": o.first_name, "email": o.email, "phone": o.phone, "whatsapp": o.phone,
            "mobile": "sms", "wa_ok": False, "lang": "ar", "reminders": True}


def link(endpoint, **kw):
    try:
        return url_for(endpoint, _external=True, **kw)
    except RuntimeError:
        base = current_app.config.get("APP_URL", "").rstrip("/")
        with current_app.test_request_context(base_url=base or "http://localhost"):
            return url_for(endpoint, _external=True, **kw)


def _render(code, lang, ctx):
    spec = CATALOG[code]
    lg = lang if lang in spec["text"] else "fr"
    vals = {k: ("" if v is None else v) for k, v in ctx.items()}
    body = spec["text"][lg].format_map(_Safe(vals))
    subject = spec["subject"][lg].format_map(_Safe(vals))
    return subject, body


class _Safe(dict):
    def __missing__(self, k):
        return ""


def _mobile_channel(r):
    if r["mobile"] == "whatsapp" and r["wa_ok"]:
        return "whatsapp"
    return "sms"


def _quiet(local):
    s, e = current_app.config["QUIET_START"], current_app.config["QUIET_END"]
    return local.hour >= s or local.hour < e


def _next_morning(local, hour):
    d = local.date() + (timedelta(days=1) if local.hour >= hour else timedelta(0))
    return datetime.combine(d, datetime.min.time()) + timedelta(hours=hour)


def _mobile_count_today(r, local):
    start = _to_utc(datetime.combine(local.date(), datetime.min.time()))
    q = Notification.query.filter(Notification.category.in_(("B", "C")), Notification.channel.in_(("sms", "whatsapp")),
                                  Notification.created_at >= start)
    if r["user_id"]:
        q = q.filter(Notification.user_id == r["user_id"])
    else:
        q = q.filter(Notification.to_masked == mask_phone(r["phone"]))
    return q.count()


def send(code, r, ctx, event_key, channel=None):
    """Crée les messages d'un événement pour un destinataire. Renvoie la liste des Notification créées."""
    spec = CATALOG[code]
    cat = spec["cat"]
    if cat == "C" and not r.get("reminders", True):
        return []
    if channel:
        channels = [channel]
    elif cat == "A":
        channels = ["email", _mobile_channel(r)]
    elif cat == "B":
        channels = ["email", _mobile_channel(r)]
    elif cat == "C":
        channels = [_mobile_channel(r)] if r.get("phone") else ["email"]
    else:
        channels = ["email"]
    local = local_now()
    created = []
    for ch in channels:
        key = f"{event_key}"[:120]
        if Notification.query.filter_by(event_key=key, channel=ch).first():
            continue                                          # RG-50 : un seul envoi par événement
        subject, body = _render(code, r["lang"], dict(ctx, prenom=r.get("name", "")))
        dest = r.get("email") if ch == "email" else (r.get("whatsapp") if ch == "whatsapp" else r.get("phone"))
        n = Notification(code=code, category=cat, channel=ch, user_id=r.get("user_id"), lang=r["lang"],
                         subject=subject, body=body, event_key=key,
                         to_masked=mask_email(dest) if ch == "email" else mask_phone(dest))
        when = None
        if cat != "A" and _quiet(local):
            when = _next_morning(local, 9 if cat == "C" else current_app.config["QUIET_END"])
        if ch != "email" and cat in ("B", "C") and _mobile_count_today(r, local) >= current_app.config["MOBILE_DAILY_CAP"]:
            when = _next_morning(local + timedelta(days=1), 9) if when is None else when + timedelta(days=1)
        db.session.add(n)
        db.session.flush()
        if when is not None:
            n.status, n.scheduled_for = "scheduled", _to_utc(when)
        else:
            _deliver(n, dest, r)
        created.append(n)
    return created


def _deliver(n, dest, r):
    """Envoi simulé : réussite sauf destination absente ou numéro de test « injoignable » (se terminant par 0000)."""
    n.attempts += 1
    digits = "".join(c for c in (dest or "") if c.isdigit())
    bad = not dest or (n.channel != "email" and (len(digits) < 9 or digits.endswith("0000")))
    if bad:
        n.status, n.error = "failed", "destination"
        other = "email" if n.channel != "email" else (_mobile_channel(r) if r.get("phone") else None)
        if other and not Notification.query.filter_by(event_key=n.event_key, channel=other).first():
            dest2 = r.get("email") if other == "email" else r.get("phone")
            if dest2:
                m = Notification(code=n.code, category=n.category, channel=other, user_id=n.user_id, lang=n.lang,
                                 subject=n.subject, body=n.body, event_key=n.event_key,
                                 to_masked=mask_email(dest2) if other == "email" else mask_phone(dest2))
                db.session.add(m)
                db.session.flush()
                m.attempts, m.status, m.sent_at = 1, "delivered", utcnow()
        return
    n.status, n.sent_at = "delivered", utcnow()


def deliver_due():
    """Envoie les messages programmés dont l'heure est passée (appelé par `flask notify-run` et la boîte d'envoi)."""
    now = utcnow()
    n = 0
    for m in Notification.query.filter(Notification.status == "scheduled", Notification.scheduled_for <= now):
        m.status, m.sent_at, m.attempts = "delivered", now, m.attempts + 1
        n += 1
    return n


def footer(lang):
    return FOOTER.get(lang, FOOTER["fr"])
