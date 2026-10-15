"""NESDA : validation de la présence (préalable à l'attestation) et suite donnée aux projets."""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..i18n import t
from ..models import AuditLog, Attendance, Enrollment, Participant, Session
from ..security import (ADMIN, COORD, DFEP, NESDA, NESDA_DG, RESP, can_see_session, roles_required,
                        visible_sessions)
from ..services import training as T

bp = Blueprint("nesda", __name__, url_prefix="/nesda")

NESDA_STATUSES = ("non_depose", "depose", "accepte", "abouti")


@bp.route("/validations")
@roles_required(ADMIN, NESDA, NESDA_DG)
def queue():
    q = visible_sessions(current_user)
    waiting = ("submitted", "wilaya_ok") if current_user.role in (NESDA_DG, ADMIN) else ("submitted",)
    pending = q.filter(Session.nesda_status.in_(waiting)).order_by(Session.nesda_submitted_at).all()
    done = (q.filter(Session.nesda_status.in_(("validated", "rejected", "wilaya_ok")))
            .order_by(Session.closed_at.desc()).limit(40).all())
    return render_template("nesda/queue.html", pending=pending, done=[s for s in done if s not in pending],
                           dg_required=T.dg_validation_required())


@bp.route("/sessions/<int:sid>", methods=["GET", "POST"])
@roles_required(ADMIN, NESDA, NESDA_DG)
def review(sid):
    s = db.session.get(Session, sid) or abort(404)
    if not can_see_session(current_user, s):
        abort(403)
    if request.method == "POST":
        act = request.form.get("action")
        ok = (T.nesda_validate(s, current_user) if act == "validate"
              else T.nesda_reject(s, current_user, request.form.get("note")) if act == "reject" else False)
        if ok:
            db.session.commit()
            flash(t("nesda.validated") if act == "validate" else t("nesda.rejected"), "ok")
            return redirect(url_for("nesda.queue"))
        flash(t("sess.action_refused"), "err")
    enrs = sorted([e for e in s.enrollments if e.status == "confirmed"],
                  key=lambda e: (e.group.name if e.group else "~", e.participant.last_name))
    stats = {e.id: T.enrollment_stats(e) for e in enrs}
    elig = {e.id: T.eligible(e, stats[e.id]) for e in enrs}
    corrections = (Attendance.query.join(Enrollment, Attendance.enrollment_id == Enrollment.id)
                   .filter(Enrollment.session_id == s.id, Attendance.corrected.is_(True)).count())
    slots = [sl for g in s.groups for sl in g.slots]
    uncalled = [sl for sl in slots if sl.day <= date.today() and sl.called_at is None]
    can_act = (current_user.role == NESDA and s.nesda_status == "submitted") or \
              (current_user.role in (NESDA_DG, ADMIN) and s.nesda_status in ("submitted", "wilaya_ok"))
    return render_template("nesda/review.html", s=s, enrs=enrs, stats=stats, elig=elig, corrections=corrections,
                           uncalled=uncalled, n_slots=len(slots), can_act=can_act)


@bp.route("/participants", methods=["GET", "POST"])
@roles_required(ADMIN, NESDA, NESDA_DG, RESP, COORD, DFEP)
def participants():
    me = current_user
    sess_ids = [s.id for s in visible_sessions(me)]
    # participants who attended at least once in my perimeter
    q = (Participant.query.join(Enrollment, Enrollment.participant_id == Participant.id)
         .join(Attendance, Attendance.enrollment_id == Enrollment.id)
         .filter(Enrollment.session_id.in_(sess_ids or [-1]), Attendance.status.in_(("present", "late")))
         .distinct())
    if request.method == "POST":
        p = db.session.get(Participant, int(request.form.get("id", -1)))
        new = request.form.get("status")
        if not p or q.filter(Participant.id == p.id).count() == 0 or new not in NESDA_STATUSES:
            abort(403)
        # CDE side may only record the deposit; acceptance and completion come from NESDA
        allowed = NESDA_STATUSES if me.role in (NESDA, NESDA_DG, ADMIN) else ("non_depose", "depose")
        if new not in allowed or (me.role not in (NESDA, NESDA_DG, ADMIN) and p.nesda_status in ("accepte", "abouti")):
            abort(403)
        p.nesda_status, p.nesda_status_on, p.nesda_updated_by_id = new, date.today(), me.id
        AuditLog.log("nesda.status", target=f"participant:{p.id}", details=new)
        db.session.commit()
        flash(t("saved"), "ok")
        return redirect(url_for("nesda.participants", st=request.args.get("st"), q=request.args.get("q")))
    st = request.args.get("st")
    if st in NESDA_STATUSES:
        q = q.filter(Participant.nesda_status == st)
    term = (request.args.get("q") or "").strip()
    if term:
        like = f"%{term}%"
        q = q.filter(Participant.last_name.ilike(like) | Participant.first_name.ilike(like) | Participant.phone.ilike(like))
    rows = q.order_by(Participant.last_name).limit(300).all()
    all_rows = (Participant.query.join(Enrollment, Enrollment.participant_id == Participant.id)
                .join(Attendance, Attendance.enrollment_id == Enrollment.id)
                .filter(Enrollment.session_id.in_(sess_ids or [-1]), Attendance.status.in_(("present", "late")))
                .with_entities(Participant.id, Participant.nesda_status).distinct().all())
    counts = {k: sum(1 for _i, s in all_rows if s == k) for k in NESDA_STATUSES}
    full = me.role in (NESDA, NESDA_DG, ADMIN)
    return render_template("nesda/participants.html", rows=rows, st=st, q=term, counts=counts, statuses=NESDA_STATUSES,
                           full=full, total=len(all_rows))
