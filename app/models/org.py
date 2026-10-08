from ..utils import utcnow

from ..extensions import db


class Wilaya(db.Model):
    __tablename__ = "wilaya"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(3), unique=True, nullable=False)          # "34"
    name_fr = db.Column(db.String(80), nullable=False)
    name_ar = db.Column(db.String(80), nullable=False)
    is_demo = db.Column(db.Boolean, default=False, nullable=False)      # fictitious data
    created_at = db.Column(db.DateTime, default=utcnow)

    institutes = db.relationship("Institute", back_populates="wilaya", order_by="Institute.code")

    def name(self, lang="fr"):
        return self.name_ar if lang == "ar" else self.name_fr


class Institute(db.Model):
    __tablename__ = "institute"
    id = db.Column(db.Integer, primary_key=True)
    wilaya_id = db.Column(db.Integer, db.ForeignKey("wilaya.id"), nullable=False, index=True)
    code = db.Column(db.String(30), unique=True, nullable=False)        # "INSFP-BBA-01"
    kind = db.Column(db.String(10), default="INSFP", nullable=False)
    name_fr = db.Column(db.String(160), nullable=False)
    name_ar = db.Column(db.String(160), nullable=False)
    address = db.Column(db.String(200))
    phone = db.Column(db.String(30))
    cde_opened_on = db.Column(db.Date)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    wilaya = db.relationship("Wilaya", back_populates="institutes")

    def name(self, lang="fr"):
        return self.name_ar if lang == "ar" else self.name_fr
