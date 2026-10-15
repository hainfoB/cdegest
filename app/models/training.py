"""Formation : référentiel, objectifs, programme, sessions, présence, satisfaction, rapports."""
import json
import secrets

from ..extensions import db
from ..utils import utcnow


def _tok():
    return secrets.token_urlsafe(16)


# ------------------------------------------------------------------ référentiel (MFEP)

class WorkshopTemplate(db.Model):
    """Formation du catalogue national."""
    __tablename__ = "workshop_template"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    theme = db.Column(db.String(60), nullable=False)               # idée, marché, gestion, juridique, numérique…
    kind = db.Column(db.String(12), default="atelier")             # atelier | bootcamp | seminaire | evenement
    title_fr = db.Column(db.String(160), nullable=False)
    title_ar = db.Column(db.String(160), nullable=False)
    objectives_fr = db.Column(db.Text)
    objectives_ar = db.Column(db.Text)
    hours = db.Column(db.Integer, default=12)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    def title(self, lang="fr"):
        return self.title_ar if lang == "ar" else self.title_fr


class SurveyQuestion(db.Model):
    """Questionnaire de satisfaction (modèle unique défini par le MFEP). Échelle 1–5."""
    __tablename__ = "survey_question"
    id = db.Column(db.Integer, primary_key=True)
    order = db.Column(db.Integer, default=0)
    text_fr = db.Column(db.String(200), nullable=False)
    text_ar = db.Column(db.String(200), nullable=False)
    text_en = db.Column(db.String(200), nullable=False)
    is_overall = db.Column(db.Boolean, default=False, nullable=False)  # question globale (taux de satisfaction)
    active = db.Column(db.Boolean, default=True, nullable=False)

    def text(self, lang="fr"):
        return {"ar": self.text_ar, "en": self.text_en}.get(lang, self.text_fr)


# ------------------------------------------------------------------ objectifs et programme

class Objective(db.Model):
    """Cible d'un KPI pour une wilaya (institute_id nul) ou un CDE, par semestre (1, 2) ou année (0)."""
    __tablename__ = "objective"
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.String(9), nullable=False, index=True)       # "2026-2027"
    semester = db.Column(db.Integer, nullable=False, default=0)      # 0 = année professionnelle
    wilaya_id = db.Column(db.Integer, db.ForeignKey("wilaya.id"), nullable=False, index=True)
    institute_id = db.Column(db.Integer, db.ForeignKey("institute.id"), index=True)
    kpi = db.Column(db.String(20), nullable=False)
    target = db.Column(db.Float, nullable=False)
    set_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (db.UniqueConstraint("year", "semester", "wilaya_id", "institute_id", "kpi", name="uq_objective"),)


class Programme(db.Model):
    __tablename__ = "programme"
    id = db.Column(db.Integer, primary_key=True)
    wilaya_id = db.Column(db.Integer, db.ForeignKey("wilaya.id"), nullable=False, index=True)
    year = db.Column(db.String(9), nullable=False)
    status = db.Column(db.String(10), default="draft")               # draft | submitted | validated | returned
    note = db.Column(db.Text)
    validated_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    validated_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)

    wilaya = db.relationship("Wilaya")
    validated_by = db.relationship("User")
    lines = db.relationship("ProgrammeLine", back_populates="programme", cascade="all, delete-orphan",
                            order_by="(ProgrammeLine.semester, ProgrammeLine.id)")

    __table_args__ = (db.UniqueConstraint("wilaya_id", "year", name="uq_programme"),)


class ProgrammeLine(db.Model):
    __tablename__ = "programme_line"
    id = db.Column(db.Integer, primary_key=True)
    programme_id = db.Column(db.Integer, db.ForeignKey("programme.id"), nullable=False, index=True)
    template_id = db.Column(db.Integer, db.ForeignKey("workshop_template.id"), nullable=False)
    institute_id = db.Column(db.Integer, db.ForeignKey("institute.id"), nullable=False)
    semester = db.Column(db.Integer, nullable=False, default=1)
    planned_groups = db.Column(db.Integer, nullable=False, default=1)

    programme = db.relationship("Programme", back_populates="lines")
    template = db.relationship("WorkshopTemplate")
    institute = db.relationship("Institute")


# ------------------------------------------------------------------ sessions

class Session(db.Model):
    """Une formation organisée par un CDE (institut). Contient modules, groupes et créneaux."""
    __tablename__ = "session"
    id = db.Column(db.Integer, primary_key=True)
    institute_id = db.Column(db.Integer, db.ForeignKey("institute.id"), nullable=False, index=True)
    template_id = db.Column(db.Integer, db.ForeignKey("workshop_template.id"))
    slug = db.Column(db.String(60), unique=True, nullable=False, default=lambda: secrets.token_hex(5))
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    mode = db.Column(db.String(8), default="onsite")                 # onsite | online | hybrid
    location = db.Column(db.String(200))
    online_url = db.Column(db.String(300))
    starts_on = db.Column(db.Date)
    ends_on = db.Column(db.Date)
    seats_per_group = db.Column(db.Integer, default=20)
    min_attendance = db.Column(db.Integer, default=80)               # % pour l'attestation
    auto_confirm = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(8), default="draft", index=True)    # draft | open | running | closed
    closed_at = db.Column(db.Date)
    # validation NESDA de la présence (préalable à l'attestation)
    nesda_status = db.Column(db.String(12), default="none", index=True)  # none | submitted | wilaya_ok | validated | rejected
    nesda_submitted_at = db.Column(db.DateTime)
    nesda_note = db.Column(db.Text)
    nesda_w_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    nesda_w_at = db.Column(db.DateTime)
    nesda_dg_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    nesda_dg_at = db.Column(db.DateTime)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=utcnow)

    institute = db.relationship("Institute")
    template = db.relationship("WorkshopTemplate")
    nesda_w_by = db.relationship("User", foreign_keys=[nesda_w_by_id])
    nesda_dg_by = db.relationship("User", foreign_keys=[nesda_dg_by_id])
    modules = db.relationship("Module", back_populates="session", cascade="all, delete-orphan", order_by="Module.order")
    groups = db.relationship("Group", back_populates="session", cascade="all, delete-orphan", order_by="Group.name")
    enrollments = db.relationship("Enrollment", back_populates="session", cascade="all, delete-orphan")

    @property
    def wilaya_id(self):
        return self.institute.wilaya_id

    @property
    def seats_total(self):
        return (self.seats_per_group or 0) * max(len(self.groups), 1)

    @property
    def confirmed(self):
        return [e for e in self.enrollments if e.status == "confirmed"]

    @property
    def certificates_open(self):
        return self.nesda_status == "validated"

    def teacher_ids(self):
        ids = {m.supervisor_id for m in self.modules if m.supervisor_id}
        for g in self.groups:
            ids |= {s.teacher_id for s in g.slots if s.teacher_id}
        return ids


class Module(db.Model):
    __tablename__ = "module"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("session.id"), nullable=False, index=True)
    order = db.Column(db.Integer, default=1)
    title = db.Column(db.String(160), nullable=False)
    hours = db.Column(db.Integer, default=3)
    supervisor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)

    session = db.relationship("Session", back_populates="modules")
    supervisor = db.relationship("User")


class Group(db.Model):
    __tablename__ = "cgroup"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("session.id"), nullable=False, index=True)
    name = db.Column(db.String(30), nullable=False)
    room = db.Column(db.String(80))

    session = db.relationship("Session", back_populates="groups")
    slots = db.relationship("Slot", back_populates="group", cascade="all, delete-orphan",
                            order_by="(Slot.day, Slot.start)")
    enrollments = db.relationship("Enrollment", back_populates="group")

    @property
    def last_day(self):
        return self.slots[-1].day if self.slots else None


class Slot(db.Model):
    """Créneau = groupe + jour + horaire + module + enseignant intervenant."""
    __tablename__ = "slot"
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("cgroup.id"), nullable=False, index=True)
    module_id = db.Column(db.Integer, db.ForeignKey("module.id"), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    day = db.Column(db.Date, nullable=False, index=True)
    start = db.Column(db.String(5), nullable=False)
    end = db.Column(db.String(5), nullable=False)
    code = db.Column(db.String(4), default=lambda: f"{secrets.randbelow(9000) + 1000}")
    called_at = db.Column(db.DateTime)                               # appel enregistré par l'enseignant

    group = db.relationship("Group", back_populates="slots")
    module = db.relationship("Module")
    teacher = db.relationship("User")
    attendances = db.relationship("Attendance", back_populates="slot", cascade="all, delete-orphan")

    @property
    def minutes(self):
        h1, m1 = map(int, self.start.split(":"))
        h2, m2 = map(int, self.end.split(":"))
        return max(0, (h2 * 60 + m2) - (h1 * 60 + m1))


# ------------------------------------------------------------------ participants

class Participant(db.Model):
    __tablename__ = "participant"
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    sex = db.Column(db.String(1))                                     # F | M
    birth_date = db.Column(db.Date)
    phone = db.Column(db.String(30), index=True)
    email = db.Column(db.String(150), index=True)
    wilaya_id = db.Column(db.Integer, db.ForeignKey("wilaya.id"), index=True)
    origin_institute_id = db.Column(db.Integer, db.ForeignKey("institute.id"))
    specialty = db.Column(db.String(120))
    status = db.Column(db.String(10), default="stagiaire")           # stagiaire | diplome
    consent_at = db.Column(db.DateTime)
    # suite NESDA : non_depose | depose | accepte | abouti
    nesda_status = db.Column(db.String(10), default="non_depose", index=True)
    nesda_status_on = db.Column(db.Date)
    nesda_updated_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=utcnow)

    wilaya = db.relationship("Wilaya")
    origin_institute = db.relationship("Institute")
    enrollments = db.relationship("Enrollment", back_populates="participant")

    @property
    def full_name(self):
        return f"{self.last_name} {self.first_name}"


class Enrollment(db.Model):
    __tablename__ = "enrollment"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("session.id"), nullable=False, index=True)
    group_id = db.Column(db.Integer, db.ForeignKey("cgroup.id"), index=True)
    participant_id = db.Column(db.Integer, db.ForeignKey("participant.id"), nullable=False, index=True)
    status = db.Column(db.String(10), default="pending", index=True)  # pending | confirmed | waitlist | cancelled
    source = db.Column(db.String(20), default="public")
    token = db.Column(db.String(40), unique=True, nullable=False, default=_tok)
    dropout = db.Column(db.Boolean, default=False, nullable=False)
    dropout_on = db.Column(db.Date)
    dropout_reason = db.Column(db.String(20))                         # desistement | absences | seuil
    cert_no = db.Column(db.String(30), unique=True)
    cert_issued_on = db.Column(db.Date)
    survey_done = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    session = db.relationship("Session", back_populates="enrollments")
    group = db.relationship("Group", back_populates="enrollments")
    participant = db.relationship("Participant", back_populates="enrollments")
    attendances = db.relationship("Attendance", back_populates="enrollment", cascade="all, delete-orphan")

    __table_args__ = (db.UniqueConstraint("session_id", "participant_id", name="uq_enrollment"),)


class Attendance(db.Model):
    __tablename__ = "attendance"
    id = db.Column(db.Integer, primary_key=True)
    slot_id = db.Column(db.Integer, db.ForeignKey("slot.id"), nullable=False, index=True)
    enrollment_id = db.Column(db.Integer, db.ForeignKey("enrollment.id"), nullable=False, index=True)
    status = db.Column(db.String(8), nullable=False)                 # present | late | absent | excused
    arrived = db.Column(db.String(5))
    left = db.Column(db.String(5))
    method = db.Column(db.String(8), default="appel")                # appel | code | correction
    marked_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    marked_at = db.Column(db.DateTime, default=utcnow)
    corrected = db.Column(db.Boolean, default=False, nullable=False)

    slot = db.relationship("Slot", back_populates="attendances")
    enrollment = db.relationship("Enrollment", back_populates="attendances")

    __table_args__ = (db.UniqueConstraint("slot_id", "enrollment_id", name="uq_attendance"),)

    @property
    def minutes(self):
        if self.status not in ("present", "late"):
            return 0
        s = self.arrived or self.slot.start
        e = self.left or self.slot.end
        h1, m1 = map(int, s.split(":"))
        h2, m2 = map(int, e.split(":"))
        return max(0, (h2 * 60 + m2) - (h1 * 60 + m1))


class SurveyResponse(db.Model):
    """Réponse anonyme : aucun lien vers le participant n'est conservé."""
    __tablename__ = "survey_response"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("session.id"), nullable=False, index=True)
    answers = db.Column(db.Text, nullable=False)                     # JSON {question_id: 1..5}
    overall = db.Column(db.Integer)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    session = db.relationship("Session")

    def answers_dict(self):
        return {int(k): v for k, v in json.loads(self.answers or "{}").items()}


# ------------------------------------------------------------------ rapports semestriels

class Report(db.Model):
    __tablename__ = "report"
    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(10), nullable=False)                 # institute | wilaya
    institute_id = db.Column(db.Integer, db.ForeignKey("institute.id"), index=True)
    wilaya_id = db.Column(db.Integer, db.ForeignKey("wilaya.id"), nullable=False, index=True)
    year = db.Column(db.String(9), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(12), default="draft")               # draft | transmitted
    snapshot = db.Column(db.Text)                                    # JSON figé
    comment = db.Column(db.Text)
    generated_at = db.Column(db.DateTime, default=utcnow)
    transmitted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    transmitted_at = db.Column(db.DateTime)

    institute = db.relationship("Institute")
    wilaya = db.relationship("Wilaya")
    transmitted_by = db.relationship("User")

    __table_args__ = (db.UniqueConstraint("level", "institute_id", "wilaya_id", "year", "semester", name="uq_report"),)

    def data(self):
        return json.loads(self.snapshot or "{}")
