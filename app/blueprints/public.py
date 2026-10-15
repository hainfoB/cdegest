"""Pages publiques : catalogue, inscription, ticket du participant, satisfaction, vérification, API."""
import json
import time
from collections import defaultdict, deque
from datetime import date

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from ..extensions import csrf, db
from ..i18n import t
from ..models import (AuditLog, Enrollment, Institute, Participant, Session, Slot, SurveyQuestion, SurveyResponse,
                      Wilaya)
from ..services import training as T
from ..utils import utcnow

bp = Blueprint("public", __name__)

_HITS = defaultdict(deque)


def _limited(bucket, per_hour):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    q = _HITS[(bucket, ip)]
    now = time.time()
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= per_hour:
        return True
    q.append(now)
    return False


def qr_svg(text, scale=5):
    import segno
    return segno.make(text, error="m").svg_inline(scale=scale, dark="#0D1B2A", border=1)


@bp.route("/formations")
def catalogue():
    wcode = request.args.get("w")
    q = Session.query.filter(Session.status == "open").join(Institute, Session.institute_id == Institute.id)
    if wcode:
        q = q.join(Wilaya, Institute.wilaya_id == Wilaya.id).filter(Wilaya.code == wcode)
    rows = q.order_by(Session.starts_on).all()
    wil_ids = {s.institute.wilaya_id for s in Session.query.filter_by(status="open")}
    return render_template("public/catalogue.html", rows=rows, wcode=wcode,
                           wilayas=Wilaya.query.filter(Wilaya.id.in_(wil_ids or [-1])).order_by(Wilaya.code).all())


@bp.route("/formations/<slug>", methods=["GET", "POST"])
def register(slug):
    s = Session.query.filter_by(slug=slug).first_or_404()
    error = None
    if request.method == "POST":
        f = request.form
        if s.status != "open":
            error = t("pub.closed")
        elif _limited("register", 20):
            error = t("login.blocked")
        elif not (f.get("last_name") and f.get("first_name") and f.get("phone") and f.get("consent")):
            error = t("form.missing")
        else:
            phone = "".join(c for c in f["phone"] if c.isdigit() or c == "+")[:20]
            p = Participant.query.filter_by(phone=phone).first() or Participant(phone=phone)
            p.last_name, p.first_name = f["last_name"].strip()[:80], f["first_name"].strip()[:80]
            p.email = (f.get("email") or "").strip()[:150] or p.email
            p.sex = f.get("sex") if f.get("sex") in ("F", "M") else p.sex
            p.birth_date = _date(f.get("birth_date")) or p.birth_date
            p.status = "diplome" if f.get("pstatus") == "diplome" else "stagiaire"
            p.specialty = (f.get("specialty") or "")[:120] or p.specialty
            w = Wilaya.query.filter_by(code=f.get("wilaya")).first()
            p.wilaya_id = w.id if w else s.institute.wilaya_id
            p.consent_at = utcnow()
            db.session.add(p)
            db.session.flush()
            e = Enrollment.query.filter_by(session_id=s.id, participant_id=p.id).first()
            if e is None:
                e = Enrollment(session=s, participant=p, source="public")
                db.session.add(e)
                T.place_enrollment(e)
                AuditLog.log("enrollment.public", target=f"session:{s.id}")
            db.session.commit()
            return redirect(url_for("public.ticket", token=e.token))
    return render_template("public/register.html", s=s, error=error,
                           wilayas=Wilaya.query.order_by(Wilaya.code).all())


def _date(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def _enr(token):
    return Enrollment.query.filter_by(token=token).first_or_404()


@bp.route("/t/<token>", methods=["GET", "POST"])
def ticket(token):
    e = _enr(token)
    s = e.session
    today = date.today()
    msg = None
    today_slots = [sl for sl in (e.group.slots if e.group else []) if sl.day == today]
    if request.method == "POST":
        code = (request.form.get("code") or "").strip()
        if _limited("code", 30):
            msg = ("err", t("login.blocked"))
        elif e.status != "confirmed":
            msg = ("err", t("pub.not_confirmed"))
        else:
            sl = next((x for x in today_slots if x.code == code), None)
            if sl is None:
                msg = ("err", t("pub.bad_code"))
            else:
                prev = next((a for a in sl.attendances if a.enrollment_id == e.id), None)
                if prev is None:
                    T.mark(sl, e, "present", None, method="code")
                    db.session.commit()
                msg = ("ok", t("pub.code_ok"))
    stats = T.enrollment_stats(e)
    finished = e.group is not None and e.group.last_day is not None and e.group.last_day <= today
    return render_template("public/ticket.html", e=e, s=s, stats=stats, msg=msg, today_slots=today_slots,
                           finished=finished, qr=qr_svg(url_for("public.ticket", token=e.token, _external=True)),
                           can_survey=finished and e.status == "confirmed" and not e.survey_done
                           and SurveyQuestion.query.filter_by(active=True).count() > 0)


@bp.route("/t/<token>/satisfaction", methods=["GET", "POST"])
def survey(token):
    e = _enr(token)
    finished = e.group is not None and e.group.last_day is not None and e.group.last_day <= date.today()
    if not finished or e.status != "confirmed" or e.survey_done:
        return redirect(url_for("public.ticket", token=token))
    qs = SurveyQuestion.query.filter_by(active=True).order_by(SurveyQuestion.order).all()
    if request.method == "POST":
        answers = {}
        for q in qs:
            v = request.form.get(f"q{q.id}")
            if v in ("1", "2", "3", "4", "5"):
                answers[q.id] = int(v)
        if len(answers) < len(qs):
            flash(t("survey.incomplete"), "err")
        else:
            overall_q = next((q for q in qs if q.is_overall), qs[-1])
            db.session.add(SurveyResponse(session_id=e.session_id, answers=json.dumps(answers),
                                          overall=answers[overall_q.id],
                                          comment=(request.form.get("comment") or "").strip()[:1000] or None))
            e.survey_done = True
            db.session.commit()
            flash(t("survey.thanks"), "ok")
            return redirect(url_for("public.ticket", token=token))
    return render_template("public/survey.html", e=e, qs=qs)


@bp.route("/verifier", methods=["GET", "POST"])
@bp.route("/verifier/<cert_no>")
def verify(cert_no=None):
    cert_no = (cert_no or request.values.get("no") or "").strip().upper()
    e = Enrollment.query.filter_by(cert_no=cert_no).first() if cert_no else None
    ok = e is not None and e.session.nesda_status == "validated"
    return render_template("public/verify.html", cert_no=cert_no, e=e if ok else None, searched=bool(cert_no))


# ------------------------------------------------------------------ integration with fp.cde.dz

def _public_session(s, lang):
    return {
        "id": s.slug,
        "title": s.title,
        "theme": s.template.theme if s.template else None,
        "institute": s.institute.name(lang),
        "wilaya": {"code": s.institute.wilaya.code, "name": s.institute.wilaya.name(lang)},
        "mode": s.mode,
        "starts_on": s.starts_on.isoformat() if s.starts_on else None,
        "ends_on": s.ends_on.isoformat() if s.ends_on else None,
        "seats": s.seats_total,
        "seats_left": max(0, s.seats_total - len(s.confirmed)),
        "register_url": url_for("public.register", slug=s.slug, _external=True),
    }


@bp.route("/api/public/sessions.json")
@csrf.exempt
def api_sessions():
    lang = request.args.get("lang", "ar")
    q = Session.query.filter_by(status="open").join(Institute, Session.institute_id == Institute.id)
    if request.args.get("w"):
        q = q.join(Wilaya, Institute.wilaya_id == Wilaya.id).filter(Wilaya.code == request.args["w"])
    resp = jsonify({"sessions": [_public_session(s, lang) for s in q.order_by(Session.starts_on)]})
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@bp.route("/embed/formations")
def embed():
    g.allow_frame = True
    rows = Session.query.filter_by(status="open").order_by(Session.starts_on).limit(12).all()
    return render_template("public/embed.html", rows=rows)
