"""Espace personnel du candidat et du stagiaire : demandes, inscriptions, attestations, messages reçus."""
from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..models import Candidature, Enrollment, Notification, Participant
from ..services import training as T

bp = Blueprint("espace", __name__, url_prefix="/mon-espace")


@bp.route("/")
@login_required
def home():
    me = current_user
    if me.is_agent and not (me.has_role("candidat") or me.has_role("stagiaire")):
        return redirect(url_for("main.dashboard"))
    cands = Candidature.query.filter_by(user_id=me.id).order_by(Candidature.created_at.desc()).all()
    parts = Participant.query.filter((Participant.user_id == me.id) | (Participant.nin_hash == me.nin_hash)).all()
    enrs = [e for p in parts for e in p.enrollments]
    enrs.sort(key=lambda e: e.session.starts_on or e.created_at.date(), reverse=True)
    stats = {e.id: T.enrollment_stats(e) for e in enrs}
    msgs = (Notification.query.filter(Notification.user_id == me.id, Notification.code != "M-01")
            .order_by(Notification.id.desc()).limit(30).all())
    in_progress = any(c.status in ("nouvelle", "retenue") for c in cands)
    return render_template("espace/home.html", cands=cands, enrs=enrs, stats=stats, msgs=msgs, in_progress=in_progress)
