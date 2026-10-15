"""Candidatures reçues par le formulaire en 4 étapes : étude par le CDE, orientation vers une session."""
from collections import Counter

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..i18n import t
from ..models import AuditLog, Candidature, Enrollment, Participant, Session
from ..security import ADMIN, COORD, DFEP, RESP, roles_required, visible_institute_ids
from ..services import training as T
from ..utils import utcnow

bp = Blueprint("candidatures", __name__, url_prefix="/candidatures")
STATUSES = ("nouvelle", "retenue", "orientee", "refusee")
PROFILES = ("decouverte", "competences", "creation", "projet")


def _scope():
    return Candidature.query.filter(Candidature.institute_id.in_(visible_institute_ids(current_user) or [-1]))


@bp.route("/")
@roles_required(ADMIN, DFEP, COORD, RESP)
def index():
    st, q = request.args.get("st"), (request.args.get("q") or "").strip()
    base = _scope()
    allc = base.all()
    counts = Counter(c.status for c in allc)
    profiles = Counter(c.profile for c in allc)
    rows = base
    if st in STATUSES:
        rows = rows.filter(Candidature.status == st)
    if q:
        like = f"%{q}%"
        rows = rows.filter(db.or_(Candidature.last_name.ilike(like), Candidature.first_name.ilike(like),
                                  Candidature.phone.ilike(like)))
    rows = rows.order_by(Candidature.created_at.desc()).limit(300).all()
    return render_template("candidatures/index.html", rows=rows, st=st, q=q, counts=counts, total=len(allc),
                           statuses=STATUSES, profiles=profiles, plist=PROFILES)


@bp.route("/<int:cid>", methods=["GET", "POST"])
@roles_required(ADMIN, DFEP, COORD, RESP)
def detail(cid):
    c = _scope().filter(Candidature.id == cid).first() or abort(404)
    sessions = (Session.query.filter(Session.institute_id == c.institute_id, Session.status == "open")
                .order_by(Session.starts_on).all())
    if request.method == "POST":
        act = request.form.get("action")
        if act == "retain" and c.status == "nouvelle":
            c.status = "retenue"
        elif act == "reject" and c.status in ("nouvelle", "retenue"):
            note = (request.form.get("note") or "").strip()
            if not note:
                flash(t("cand.need_reason"), "err")
                return redirect(url_for(".detail", cid=c.id))
            c.status, c.note = "refusee", note[:500]
        elif act == "orient" and c.status in ("nouvelle", "retenue"):
            s = next((x for x in sessions if x.id == request.form.get("session", type=int)), None)
            if not s:
                abort(400)
            c.enrollment = _enroll(c, s)
            c.status = "orientee"
        else:
            abort(400)
        c.reviewed_by_id, c.reviewed_at = current_user.id, utcnow()
        AuditLog.log(f"candidature.{c.status}", target=f"candidature:{c.id}", details=c.note or "")
        db.session.commit()
        flash(t("saved"), "ok")
        return redirect(url_for(".detail", cid=c.id))
    return render_template("candidatures/detail.html", c=c, sessions=sessions)


def _enroll(c, s):
    p = Participant.query.filter_by(phone=c.phone).first() if c.phone else None
    p = p or Participant(phone=c.phone)
    p.last_name, p.first_name, p.email = c.last_name, c.first_name, c.email or p.email
    p.sex, p.birth_date = c.sex or p.sex, c.birth_date or p.birth_date
    p.wilaya_id, p.origin_institute_id = c.wilaya_id, c.origin_institute_id or p.origin_institute_id
    p.specialty, p.status, p.consent_at = c.specialty, c.pstatus, c.consent_at
    db.session.add(p)
    db.session.flush()
    e = Enrollment.query.filter_by(session_id=s.id, participant_id=p.id).first()
    if e is None:
        e = Enrollment(session=s, participant=p, source="candidature")
        db.session.add(e)
        T.place_enrollment(e)
    db.session.flush()
    return e
