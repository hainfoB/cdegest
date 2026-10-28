"""Site public : événements des CDE et signalements (plateforme de support)."""
import secrets

from ..extensions import db
from ..utils import utcnow


class Event(db.Model):
    """Événement publié par un CDE, une wilaya ou le MFEP (journée portes ouvertes, salon, concours…)."""
    __tablename__ = "event"
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), default="evenement", nullable=False)   # evenement | portes_ouvertes | salon | concours | annonce
    title_fr = db.Column(db.String(160), nullable=False)
    title_ar = db.Column(db.String(160), nullable=False)
    body_fr = db.Column(db.Text)
    body_ar = db.Column(db.Text)
    starts_on = db.Column(db.Date, nullable=False, index=True)
    ends_on = db.Column(db.Date)
    place = db.Column(db.String(160))
    wilaya_id = db.Column(db.Integer, db.ForeignKey("wilaya.id"), index=True)       # vide = national
    institute_id = db.Column(db.Integer, db.ForeignKey("institute.id"), index=True)  # vide = toute la wilaya
    published = db.Column(db.Boolean, default=False, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=utcnow)

    wilaya = db.relationship("Wilaya")
    institute = db.relationship("Institute")
    created_by = db.relationship("User")

    def title(self, lang="fr"):
        return self.title_ar if lang == "ar" and self.title_ar else self.title_fr

    def body(self, lang="fr"):
        return (self.body_ar if lang == "ar" and self.body_ar else self.body_fr) or ""


def _ref():
    return "S" + secrets.token_hex(3).upper()


class Ticket(db.Model):
    """Signalement d'un problème ou demande d'aide, déposé depuis le site public."""
    __tablename__ = "ticket"
    id = db.Column(db.Integer, primary_key=True)
    ref = db.Column(db.String(12), unique=True, nullable=False, default=_ref)
    token = db.Column(db.String(32), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(16))
    category = db.Column(db.String(20), nullable=False)       # inscription | compte | session | presence | attestation | technique | autre
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(150))
    wilaya_id = db.Column(db.Integer, db.ForeignKey("wilaya.id"), index=True)
    institute_id = db.Column(db.Integer, db.ForeignKey("institute.id"), index=True)
    subject = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(12), default="open", nullable=False)   # open | progress | resolved | closed
    reply = db.Column(db.Text)
    handled_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    handled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    wilaya = db.relationship("Wilaya")
    institute = db.relationship("Institute")
    handled_by = db.relationship("User")
