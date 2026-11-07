"""Roles, perimeters and access decorators.

Every screen that lists data must go through the scope helpers below:
no blueprint is allowed to query Institute/User/Session/... without them.
"""
from functools import wraps

from flask import abort
from flask_login import current_user, login_required

from datetime import date

from ..extensions import db
from ..models import Habilitation, Institute, Module, Session, Slot, User, Wilaya, Group

ADMIN, MFEP, DFEP, COORD, RESP, TEACHER = "admin", "mfep", "dfep", "coord", "resp", "formateur"
NESDA, NESDA_DG = "nesda", "nesda_dg"
CANDIDAT, STAGIAIRE = "candidat", "stagiaire"
ROLES = (ADMIN, MFEP, DFEP, COORD, RESP, TEACHER, NESDA_DG, NESDA)
PUBLIC = {CANDIDAT, STAGIAIRE}

LEVEL = {ADMIN: "platform", MFEP: "national", NESDA_DG: "national", DFEP: "wilaya", COORD: "wilaya",
         NESDA: "wilaya", RESP: "institute", TEACHER: "institute", CANDIDAT: "self", STAGIAIRE: "self"}

NATIONAL = {ADMIN, MFEP, NESDA_DG}
WILAYA_LEVEL = {DFEP, COORD, NESDA}
NEEDS_WILAYA = {DFEP, COORD, NESDA}
NEEDS_INSTITUTE = {RESP, TEACHER}

# Qui accorde quel rôle (CDC fonctionnel v1.3, tableau 5.1 ; validé le 07/11/2026)
CAN_CREATE = {
    ADMIN: set(ROLES),
    MFEP: {MFEP, DFEP, NESDA_DG},
    NESDA_DG: {NESDA},
    DFEP: {COORD, RESP},
    COORD: {RESP},
    RESP: {TEACHER},
    TEACHER: set(),
    NESDA: set(),
    CANDIDAT: set(),
    STAGIAIRE: set(),
}
CAN_GRANT = CAN_CREATE

# The MFEP sees aggregates only — never personal data (loi 18-07)
AGGREGATE_ONLY = {MFEP}

# Who manages sessions of an institute
SESSION_MANAGERS = {ADMIN, RESP}
# Who prints certificates: the NESDA representative, once attendance is validated
CERT_PRINTERS = {ADMIN, NESDA, NESDA_DG}
# Who validates attendance for NESDA
NESDA_VALIDATORS = {NESDA, NESDA_DG, ADMIN}

ALL = set(ROLES)
# Sidebar: (endpoint, icon, i18n key, roles)
NAV = [
    ("main.dashboard", "grid", "nav.dashboard", ALL),
    ("espace.home", "user", "nav.espace", PUBLIC),
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
    ("site.manage_events", "calendar", "nav.events", {ADMIN, MFEP, DFEP, COORD, RESP}),
    ("site.manage_tickets", "message", "nav.tickets", {ADMIN, DFEP, COORD, RESP, NESDA, NESDA_DG}),
    ("main.integration", "globe", "nav.integration", {ADMIN, MFEP}),
    ("integration.connectors", "repeat", "nav.connectors", {ADMIN, MFEP}),
    ("integration.outbox", "message", "nav.outbox", {ADMIN, MFEP, DFEP, COORD, RESP}),
]


def nav_for(user):
    if user.role in PUBLIC:
        return [n for n in NAV if n[0] == "espace.home"]
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


def visible_habilitations(user):
    """Habilitations d'agents que le rôle actif peut voir (les candidats et stagiaires n'y figurent pas)."""
    q = Habilitation.query.filter(Habilitation.role.in_(ROLES))
    r = user.role
    if r == ADMIN:
        return q
    if r == MFEP:
        return q.filter(Habilitation.role.in_((MFEP, DFEP, COORD, NESDA_DG)))
    if r == NESDA_DG:
        return q.filter(Habilitation.role.in_((NESDA_DG, NESDA)))
    if r in (DFEP, COORD):
        inst_ids = visible_institute_ids(user)
        return q.filter(
            ((Habilitation.wilaya_id == (user.wilaya_id or -1)) & Habilitation.role.in_((DFEP, COORD, RESP, TEACHER, NESDA)))
            | (Habilitation.institute_id.in_(inst_ids or [-1]))
        )
    if r == RESP:
        return q.filter(Habilitation.institute_id == (user.institute_id or -1))
    return q.filter(Habilitation.user_id == user.id)


def visible_users(user):
    """Personnes ayant au moins une habilitation visible."""
    ids = visible_habilitations(user).with_entities(Habilitation.user_id)
    q = User.query.filter(User.id.in_(ids))
    if user.role in (TEACHER, NESDA) or user.role in PUBLIC:
        q = User.query.filter(User.id == user.id)
    return q


def roles_on_institute(user, institute_id):
    """Rôles valides d'une personne sur un CDE (séparation des fonctions, RG-36)."""
    today = date.today()
    return {h.role for h in user.habilitations if h.is_valid(today) and h.institute_id == institute_id}


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
    if user.role in PUBLIC:
        return {"ar": "فضائي الشخصي", "fr": "Mon espace", "en": "My space"}[lang]
    if user.role in NATIONAL:
        return {"ar": "المستوى الوطني", "fr": "Niveau national", "en": "National level"}[lang]
    if user.institute is not None:
        return user.institute.name(lang)
    if user.wilaya is not None:
        prefix = {"ar": "ولاية ", "fr": "Wilaya de ", "en": "Wilaya of "}[lang]
        return prefix + user.wilaya.name(lang)
    return "—"
