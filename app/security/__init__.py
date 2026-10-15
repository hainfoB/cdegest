"""Roles, perimeters and access decorators.

Every screen that lists data must go through the scope helpers below:
no blueprint is allowed to query Institute/User/Session/... without them.
"""
from functools import wraps

from flask import abort
from flask_login import current_user, login_required

from ..models import Institute, Module, Session, Slot, User, Wilaya, Group

ADMIN, MFEP, DFEP, COORD, RESP, TEACHER = "admin", "mfep", "dfep", "coord", "resp", "formateur"
NESDA, NESDA_DG = "nesda", "nesda_dg"
ROLES = (ADMIN, MFEP, DFEP, COORD, RESP, TEACHER, NESDA_DG, NESDA)

LEVEL = {ADMIN: "platform", MFEP: "national", NESDA_DG: "national", DFEP: "wilaya", COORD: "wilaya",
         NESDA: "wilaya", RESP: "institute", TEACHER: "institute"}

NATIONAL = {ADMIN, MFEP, NESDA_DG}
WILAYA_LEVEL = {DFEP, COORD, NESDA}
NEEDS_WILAYA = {DFEP, COORD, NESDA}
NEEDS_INSTITUTE = {RESP, TEACHER}

# Who may create which accounts
CAN_CREATE = {
    ADMIN: set(ROLES),
    MFEP: {DFEP, COORD},
    NESDA_DG: {NESDA},
    DFEP: {COORD, RESP, TEACHER},
    COORD: {RESP, TEACHER},
    RESP: {TEACHER},
    TEACHER: set(),
    NESDA: set(),
}

# The MFEP sees aggregates only — never personal data (loi 18-07)
AGGREGATE_ONLY = {MFEP}

# Who manages sessions of an institute
SESSION_MANAGERS = {ADMIN, RESP}
# Who prints certificates (CDE of the wilaya, after NESDA validation)
CERT_PRINTERS = {ADMIN, RESP, COORD, DFEP}
# Who validates attendance for NESDA
NESDA_VALIDATORS = {NESDA, NESDA_DG, ADMIN}

ALL = set(ROLES)
# Sidebar: (endpoint, icon, i18n key, roles)
NAV = [
    ("main.dashboard", "grid", "nav.dashboard", ALL),
    ("main.compare", "columns", "nav.compare", {ADMIN, MFEP}),
    ("sessions.my_slots", "qr", "nav.myslots", {TEACHER}),
    ("candidatures.index", "user-check", "nav.candidatures", {ADMIN, DFEP, COORD, RESP}),
    ("sessions.index", "layers", "nav.sessions", {ADMIN, DFEP, COORD, RESP, TEACHER}),
    ("nesda.queue", "check", "nav.nesda_queue", {ADMIN, NESDA, NESDA_DG}),
    ("nesda.participants", "thumb", "nav.nesda_people", {ADMIN, NESDA, NESDA_DG, RESP, COORD, DFEP}),
    ("org.objectives", "target", "nav.objectives", {ADMIN, MFEP, DFEP, COORD, RESP}),
    ("org.programme", "calendar", "nav.programme", {ADMIN, DFEP, COORD, RESP}),
    ("reports.index", "file", "nav.reports", {ADMIN, MFEP, DFEP, COORD, RESP}),
    ("org.surveys", "smile", "nav.surveys", {ADMIN, MFEP, DFEP, COORD, RESP, NESDA_DG}),
    ("org.referentiel", "book", "nav.referentiel", {ADMIN, MFEP, DFEP, COORD, RESP}),
    ("org.institutes", "building", "nav.institutes", {ADMIN, MFEP, DFEP, COORD, NESDA_DG, NESDA}),
    ("org.users", "users", "nav.users", {ADMIN, MFEP, DFEP, COORD, RESP, NESDA_DG}),
    ("org.audit", "shield", "nav.audit", {ADMIN, MFEP, DFEP, COORD, RESP, NESDA_DG}),
    ("main.integration", "globe", "nav.integration", {ADMIN, MFEP}),
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


def sees_people(user):
    """Nominative data (participants) are hidden from the national ministry level."""
    return user.role not in AGGREGATE_ONLY


# ---------- perimeters ----------

def visible_wilayas(user):
    q = Wilaya.query
    if user.role in NATIONAL:
        return q.order_by(Wilaya.code)
    w = user.scope_wilaya
    return q.filter(Wilaya.id == (w.id if w else -1))


def visible_institutes(user, include_inactive=False):
    q = Institute.query
    if not include_inactive:
        q = q.filter(Institute.active.is_(True))
    if user.role in NATIONAL:
        return q.order_by(Institute.code)
    if user.role in WILAYA_LEVEL:
        return q.filter(Institute.wilaya_id == (user.wilaya_id or -1)).order_by(Institute.code)
    return q.filter(Institute.id == (user.institute_id or -1))


def visible_institute_ids(user):
    return [i.id for i in visible_institutes(user, include_inactive=True)]


def visible_users(user):
    q = User.query
    if user.role == ADMIN:
        return q
    if user.role == MFEP:
        return q.filter(User.role.in_((MFEP, DFEP, COORD)))
    if user.role == NESDA_DG:
        return q.filter(User.role.in_((NESDA_DG, NESDA)))
    if user.role in (DFEP, COORD):
        inst_ids = visible_institute_ids(user)
        return q.filter(
            ((User.wilaya_id == user.wilaya_id) & User.role.in_((DFEP, COORD, RESP, TEACHER, NESDA)))
            | (User.institute_id.in_(inst_ids or [-1]))
        )
    if user.role == RESP:
        return q.filter(User.institute_id == user.institute_id)
    return q.filter(User.id == user.id)


def visible_sessions(user):
    q = Session.query
    if user.role in (ADMIN, NESDA_DG):
        return q
    if user.role == MFEP:
        return q.filter(Session.id == -1)          # aggregates only
    if user.role == TEACHER:
        sup = Module.query.with_entities(Module.session_id).filter(Module.supervisor_id == user.id)
        taught = (Slot.query.join(Group, Slot.group_id == Group.id)
                  .with_entities(Group.session_id).filter(Slot.teacher_id == user.id))
        return q.filter(Session.id.in_(sup) | Session.id.in_(taught))
    return q.filter(Session.institute_id.in_(visible_institute_ids(user) or [-1]))


def can_see_session(user, s):
    return visible_sessions(user).filter(Session.id == s.id).count() == 1


def can_manage_session(user, s):
    return user.role == ADMIN or (user.role == RESP and s.institute_id == user.institute_id)


def scope_label(user, lang):
    if user.role in NATIONAL:
        return {"ar": "المستوى الوطني", "fr": "Niveau national", "en": "National level"}[lang]
    if user.institute is not None:
        return user.institute.name(lang)
    if user.wilaya is not None:
        prefix = {"ar": "ولاية ", "fr": "Wilaya de ", "en": "Wilaya of "}[lang]
        return prefix + user.wilaya.name(lang)
    return "—"
