"""Messages (EP-11), connecteurs vers les administrations et journal des échanges (EP-12)."""
from ..extensions import db
from ..utils import utcnow


class Notification(db.Model):
    """Un message à envoyer ou envoyé. En mode simulé, il reste dans la boîte d'envoi (aucun envoi réel)."""
    __tablename__ = "notification"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(5), nullable=False, index=True)            # M-01 … M-18
    category = db.Column(db.String(1), nullable=False, index=True)        # A sécurité | B dossier | C rappel | D agents
    channel = db.Column(db.String(8), nullable=False, index=True)         # email | whatsapp | sms
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    to_masked = db.Column(db.String(80))
    lang = db.Column(db.String(2), default="ar")
    subject = db.Column(db.String(160))
    body = db.Column(db.Text, nullable=False)
    event_key = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(10), default="queued", nullable=False, index=True)  # queued | scheduled | delivered | failed | skipped
    scheduled_for = db.Column(db.DateTime, index=True)
    sent_at = db.Column(db.DateTime)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    error = db.Column(db.String(120))
    simulated = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    user = db.relationship("User")

    __table_args__ = (db.UniqueConstraint("event_key", "channel", name="uq_notification_event"),)


class Connector(db.Model):
    """Partenaire d'échange et son mode : simule | reel | desactive (US-1201)."""
    __tablename__ = "connector"
    code = db.Column(db.String(20), primary_key=True)        # etat_civil | mfep_diplomes | mfep_stage | men | nesda | mfep_stats
    mode = db.Column(db.String(10), default="simule", nullable=False)
    url = db.Column(db.String(200))
    updated_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    updated_at = db.Column(db.DateTime)


class ApiCall(db.Model):
    """Trace de chaque échange, entrant ou sortant, sans NIN en clair."""
    __tablename__ = "api_call"
    id = db.Column(db.Integer, primary_key=True)
    connector = db.Column(db.String(20), nullable=False, index=True)
    direction = db.Column(db.String(4), nullable=False)      # in (CDEgest reçoit) | out (CDEgest fournit)
    mode = db.Column(db.String(10), nullable=False)
    nin_hash = db.Column(db.String(64), index=True)
    fields = db.Column(db.String(200))
    result = db.Column(db.String(20), nullable=False)        # trouve | inconnu | indisponible | desactive | servi | refuse
    duration_ms = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=utcnow, index=True)


class AppMeta(db.Model):
    __tablename__ = "app_meta"
    key = db.Column(db.String(40), primary_key=True)
    value = db.Column(db.String(200))
