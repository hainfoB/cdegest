from ..utils import utcnow

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(30))
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(12), nullable=False, index=True)
    wilaya_id = db.Column(db.Integer, db.ForeignKey("wilaya.id"), index=True)
    institute_id = db.Column(db.Integer, db.ForeignKey("institute.id"), index=True)
    lang = db.Column(db.String(2), default="ar")
    active = db.Column(db.Boolean, default=True, nullable=False)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)

    wilaya = db.relationship("Wilaya")
    institute = db.relationship("Institute")

    # Flask-Login
    @property
    def is_active(self):
        return self.active

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    @property
    def scope_wilaya(self):
        """Wilaya the user is attached to (directly or through the institute)."""
        if self.institute is not None:
            return self.institute.wilaya
        return self.wilaya
