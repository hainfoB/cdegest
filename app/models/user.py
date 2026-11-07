"""Identité : une personne = un NIN = un compte ; un compte porte une ou plusieurs habilitations (rôle + périmètre).

Le rôle actif (choisi à la connexion) détermine seul les droits : `user.role`, `user.wilaya_id`,
`user.institute_id` renvoient les valeurs de l'habilitation active (RG-34, RG-35).
"""
import json
import secrets
from datetime import date, timedelta

from flask import has_request_context, session
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .. import nin as NIN
from ..extensions import db
from ..utils import utcnow

AGENT_ROLES = ("admin", "mfep", "dfep", "coord", "resp", "formateur", "nesda", "nesda_dg")
PUBLIC_ROLES = ("candidat", "stagiaire")
# ordre de préférence quand aucun rôle n'a encore été choisi
ROLE_ORDER = ("admin", "mfep", "nesda_dg", "dfep", "coord", "nesda", "resp", "formateur", "stagiaire", "candidat")


class User(UserMixin, db.Model):
    """Le compte d'une personne. Le NIN est chiffré ; l'empreinte HMAC sert à la recherche."""
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    nin_hash = db.Column(db.String(64), unique=True, index=True)
    nin_enc = db.Column(db.Text)
    name = db.Column(db.String(120), nullable=False)
    birth_date = db.Column(db.Date)
    sex = db.Column(db.String(1))
    identity_source = db.Column(db.String(12), default="declaratif")   # etat_civil | simule | declaratif
    identity_checked_at = db.Column(db.DateTime)
    email = db.Column(db.String(150), index=True)
    phone = db.Column(db.String(30))
    whatsapp = db.Column(db.String(30))
    mobile_channel = db.Column(db.String(8), default="sms")            # whatsapp | sms
    code_channel = db.Column(db.String(8), default="email")            # email | whatsapp | sms
    email_verified_at = db.Column(db.DateTime)
    phone_verified_at = db.Column(db.DateTime)
    wa_consent_at = db.Column(db.DateTime)
    reminders = db.Column(db.Boolean, default=True, nullable=False)    # catégorie C (US-1105)
    password_hash = db.Column(db.String(256), nullable=False)
    lang = db.Column(db.String(2), default="ar")
    active = db.Column(db.Boolean, default=True, nullable=False)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    failed_logins = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime)
    invite_token = db.Column(db.String(64), unique=True)
    invite_expires = db.Column(db.DateTime)
    charter_at = db.Column(db.DateTime)
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)

    habilitations = db.relationship("Habilitation", back_populates="user", foreign_keys="Habilitation.user_id",
                                    cascade="all, delete-orphan", order_by="Habilitation.id")

    # ---------------------------------------------------------------- NIN
    @property
    def nin(self):
        return NIN.decrypt(self.nin_enc)

    @nin.setter
    def nin(self, raw):
        self.nin_hash = NIN.fingerprint(raw)
        self.nin_enc = NIN.encrypt(raw)

    @property
    def nin_masked(self):
        return NIN.mask(self.nin)

    @classmethod
    def by_nin(cls, raw):
        h = NIN.fingerprint(raw)
        return cls.query.filter_by(nin_hash=h).first() if h else None

    # ---------------------------------------------------------------- password, lock
    @property
    def is_active(self):
        return self.active

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    @property
    def locked(self):
        return self.locked_until is not None and self.locked_until > utcnow()

    # ---------------------------------------------------------------- habilitations
    def valid_habilitations(self, on=None):
        on = on or date.today()
        return [h for h in self.habilitations if h.is_valid(on)]

    def agent_habilitations(self):
        return [h for h in self.valid_habilitations() if h.role in AGENT_ROLES]

    def has_role(self, role):
        return any(h.role == role for h in self.valid_habilitations())

    def grant(self, role, institute=None, wilaya=None, by=None, reason=None, ends_on=None, activated=True):
        """Ajoute une habilitation (ou renvoie celle qui existe déjà, identique et valide)."""
        if institute is not None and wilaya is None:
            wilaya = institute.wilaya
        for h in self.habilitations:
            if (h.role == role and h.institute_id == (institute.id if institute else None)
                    and h.wilaya_id == (wilaya.id if wilaya else None) and h.status in ("active", "pending")):
                return h
        h = Habilitation(user=self, role=role, institute=institute, wilaya=wilaya, granted_by=by,
                         reason=(reason or "")[:200] or None, ends_on=ends_on,
                         status="active" if activated else "pending")
        db.session.add(h)
        self._active_hab = None
        return h

    def use(self, hab):
        """Fixe le rôle actif (session web et objet en mémoire)."""
        self._active_hab = hab
        if has_request_context():
            session["hab"] = hab.id if hab is not None else None
        return self

    @property
    def active_hab(self):
        h = getattr(self, "_active_hab", None)
        if h is not None and h.user_id in (None, self.id) and h.is_valid():
            return h
        valid = self.valid_habilitations()
        h = None
        if has_request_context() and session.get("hab"):
            h = next((x for x in valid if x.id == session["hab"]), None)
        if h is None and valid:
            h = sorted(valid, key=lambda x: ROLE_ORDER.index(x.role) if x.role in ROLE_ORDER else 99)[0]
        self._active_hab = h
        return h

    @property
    def role(self):
        h = self.active_hab
        return h.role if h else None

    @property
    def wilaya_id(self):
        h = self.active_hab
        return h.wilaya_id if h else None

    @property
    def institute_id(self):
        h = self.active_hab
        return h.institute_id if h else None

    @property
    def wilaya(self):
        h = self.active_hab
        return h.wilaya if h else None

    @property
    def institute(self):
        h = self.active_hab
        return h.institute if h else None

    @property
    def scope_wilaya(self):
        """Wilaya du rôle actif (directement ou par l'institut)."""
        if self.institute is not None:
            return self.institute.wilaya
        return self.wilaya

    @property
    def is_agent(self):
        return self.role in AGENT_ROLES

    @classmethod
    def having(cls, role, institute_id=None, wilaya_id=None, active_only=True):
        """Comptes qui détiennent une habilitation valide `role` (optionnellement sur un périmètre)."""
        q = cls.query.join(Habilitation, Habilitation.user_id == cls.id).filter(Habilitation.role == role,
                                                                                Habilitation.status == "active")
        today = date.today()
        q = q.filter(db.or_(Habilitation.ends_on.is_(None), Habilitation.ends_on >= today))
        if institute_id is not None:
            q = q.filter(Habilitation.institute_id == institute_id)
        if wilaya_id is not None:
            q = q.filter(Habilitation.wilaya_id == wilaya_id)
        if active_only:
            q = q.filter(cls.active.is_(True))
        return q.distinct()

    # ---------------------------------------------------------------- contact
    @property
    def mobile_number(self):
        return (self.whatsapp or self.phone) if self.mobile_channel == "whatsapp" else self.phone

    def channels(self):
        """Canaux vérifiés utilisables pour un code (ES-11)."""
        out = []
        if self.email:
            out.append("email")
        if self.whatsapp or self.phone:
            out.append("whatsapp" if self.mobile_channel == "whatsapp" and self.wa_consent_at else "sms")
        return out

    def new_invite(self, hours=72):
        self.invite_token = secrets.token_urlsafe(32)
        self.invite_expires = utcnow() + timedelta(hours=hours)
        return self.invite_token


class Habilitation(db.Model):
    """Droit d'exercer un rôle sur un périmètre pendant une période (RG-34)."""
    __tablename__ = "habilitation"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    role = db.Column(db.String(12), nullable=False, index=True)
    wilaya_id = db.Column(db.Integer, db.ForeignKey("wilaya.id"), index=True)
    institute_id = db.Column(db.Integer, db.ForeignKey("institute.id"), index=True)
    status = db.Column(db.String(10), default="active", nullable=False, index=True)  # pending | active | suspended | revoked
    starts_on = db.Column(db.Date, default=date.today)
    ends_on = db.Column(db.Date)
    reason = db.Column(db.String(200))
    granted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    granted_at = db.Column(db.DateTime, default=utcnow)
    changed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    changed_at = db.Column(db.DateTime)
    change_reason = db.Column(db.String(200))

    user = db.relationship("User", back_populates="habilitations", foreign_keys=[user_id])
    granted_by = db.relationship("User", foreign_keys=[granted_by_id])
    changed_by = db.relationship("User", foreign_keys=[changed_by_id])
    wilaya = db.relationship("Wilaya")
    institute = db.relationship("Institute")

    def is_valid(self, on=None):
        on = on or date.today()
        return (self.status == "active" and (self.starts_on is None or self.starts_on <= on)
                and (self.ends_on is None or self.ends_on >= on))

    def scope_name(self, lang="fr"):
        if self.role == "candidat":
            return {"ar": "ملفي الشخصي", "fr": "Mon dossier", "en": "My file"}[lang]
        if self.institute is not None:
            return self.institute.name(lang)
        if self.wilaya is not None:
            return {"ar": "ولاية ", "fr": "Wilaya de ", "en": "Wilaya of "}[lang] + self.wilaya.name(lang)
        return {"ar": "المستوى الوطني", "fr": "National", "en": "National"}[lang]


class OtpCode(db.Model):
    """Code à usage unique : 6 chiffres, 5 min, 5 essais, haché (ES-11)."""
    __tablename__ = "otp_code"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    purpose = db.Column(db.String(12), default="login")        # login | activate | reset | channel
    channel = db.Column(db.String(8), nullable=False)
    code_hash = db.Column(db.String(256), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    used_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    user = db.relationship("User")


class Device(db.Model):
    """Appareil reconnu : pas de code pour un candidat ou un stagiaire sur un appareil déjà vérifié."""
    __tablename__ = "user_device"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, index=True)
    label = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=utcnow)
    last_seen = db.Column(db.DateTime, default=utcnow)


def prefs_json(u):
    return json.dumps({"reminders": u.reminders, "mobile": u.mobile_channel, "code": u.code_channel})
