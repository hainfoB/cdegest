from ..utils import utcnow

from flask import request
from flask_login import current_user

from ..extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_log"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    user_label = db.Column(db.String(150))
    action = db.Column(db.String(60), nullable=False)
    target = db.Column(db.String(80))
    details = db.Column(db.String(300))
    wilaya_id = db.Column(db.Integer, db.ForeignKey("wilaya.id"), index=True)
    institute_id = db.Column(db.Integer, db.ForeignKey("institute.id"), index=True)
    ip = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    @classmethod
    def log(cls, action, target=None, details=None, user=None):
        u = user or (current_user if current_user and current_user.is_authenticated else None)
        entry = cls(
            action=action,
            target=target,
            details=(details or "")[:300],
            user_id=getattr(u, "id", None),
            user_label=getattr(u, "email", None),
            wilaya_id=getattr(getattr(u, "scope_wilaya", None), "id", None),
            institute_id=getattr(u, "institute_id", None),
            ip=(request.headers.get("X-Forwarded-For", request.remote_addr) or "")[:45] if request else None,
        )
        db.session.add(entry)
        return entry
