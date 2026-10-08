"""Roles, perimeters and access decorators.

Every screen that lists data must go through the scope helpers below:
no blueprint is allowed to query Institute/User/... without them.
"""
from functools import wraps

from flask import abort
from flask_login import current_user, login_required

from ..models import Institute, User, Wilaya

ADMIN, MFEP, DFEP, COORD, RESP, TEACHER = "admin", "mfep", "dfep", "coord", "resp", "formateur"
ROLES = (ADMIN, MFEP, DFEP, COORD, RESP, TEACHER)

# Level of each role in the hierarchy (used for display and for who-manages-whom)
LEVEL = {ADMIN: "platform", MFEP: "national", DFEP: "wilaya", COORD: "wilaya", RESP: "institute", TEACHER: "institute"}

# Roles that must be attached to a wilaya / an institute
NEEDS_WILAYA = {DFEP, COORD}
NEEDS_INSTITUTE = {RESP, TEACHER}

# Roles each role may create (étape 3)
CAN_CREATE = {
    ADMIN: set(ROLES),
    MFEP: {DFEP, COORD},
    DFEP: {COORD, RESP, TEACHER},
    COORD: {RESP, TEACHER},
    RESP: {TEACHER},
    TEACHER: set(),
}

# The national level sees aggregates only — never personal data (loi 18-07)
AGGREGATE_ONLY = {MFEP}

# Sidebar: (endpoint or None if not built yet, icon, i18n key, roles, step where it arrives)
NAV = [
    ("main.dashboard", "grid", "nav.dashboard", set(ROLES), None),
    (None, "book", "nav.referentiel", {ADMIN, MFEP, DFEP, COORD, RESP}, 3),
    (None, "target", "nav.objectives", {ADMIN, MFEP, DFEP, COORD}, 3),
    (None, "calendar", "nav.programme", {ADMIN, DFEP, COORD, RESP}, 3),
    (None, "building", "nav.institutes", {ADMIN, MFEP, DFEP, COORD}, 3),
    (None, "users", "nav.users", {ADMIN, MFEP, DFEP, COORD, RESP}, 3),
    (None, "layers", "nav.sessions", {ADMIN, DFEP, COORD, RESP, TEACHER}, 4),
    (None, "qr", "nav.attendance", {ADMIN, DFEP, COORD, RESP, TEACHER}, 4),
    (None, "award", "nav.certificates", {ADMIN, DFEP, COORD, RESP}, 4),
    (None, "smile", "nav.surveys", {ADMIN, MFEP, DFEP, COORD, RESP}, 5),
    (None, "file", "nav.reports", {ADMIN, MFEP, DFEP, COORD, RESP}, 6),
    (None, "shield", "nav.audit", {ADMIN, MFEP, DFEP, COORD, RESP}, 3),
]


def nav_for(user):
    return [n for n in NAV if user.role in n[3]]


def roles_required(*roles):
    """Login + role check. Unknown or inactive users get 403."""
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*a, **kw):
            if current_user.role not in roles:
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco


# ---------- perimeters ----------

def visible_wilayas(user):
    q = Wilaya.query
    if user.role in (ADMIN, MFEP):
        return q.order_by(Wilaya.code)
    w = user.scope_wilaya
    return q.filter(Wilaya.id == (w.id if w else -1))


def visible_institutes(user):
    q = Institute.query.filter(Institute.active.is_(True))
    if user.role in (ADMIN, MFEP):
        return q.order_by(Institute.code)
    if user.role in (DFEP, COORD):
        return q.filter(Institute.wilaya_id == (user.wilaya_id or -1)).order_by(Institute.code)
    return q.filter(Institute.id == (user.institute_id or -1))


def visible_users(user):
    """Accounts a user may see. MFEP sees wilaya-level accounts only (no trainer lists)."""
    q = User.query
    if user.role == ADMIN:
        return q
    if user.role == MFEP:
        return q.filter(User.role.in_((MFEP, DFEP, COORD)))
    if user.role in (DFEP, COORD):
        inst_ids = [i.id for i in visible_institutes(user)]
        return q.filter(
            (User.wilaya_id == user.wilaya_id) | (User.institute_id.in_(inst_ids or [-1]))
        )
    if user.role == RESP:
        return q.filter(User.institute_id == user.institute_id)
    return q.filter(User.id == user.id)


def scope_label(user, lang):
    """Human label of the user's perimeter, for the header."""
    if user.role in (ADMIN, MFEP):
        return {"ar": "المستوى الوطني", "fr": "Niveau national", "en": "National level"}[lang]
    if user.institute is not None:
        return user.institute.name(lang)
    if user.wilaya is not None:
        prefix = {"ar": "ولاية ", "fr": "Wilaya de ", "en": "Wilaya of "}[lang]
        return prefix + user.wilaya.name(lang)
    return "—"
