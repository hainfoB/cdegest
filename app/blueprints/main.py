from datetime import date

from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Enrollment, Group, Module, Objective, Programme, Report, Session, Slot, Wilaya
from ..security import (ADMIN, COORD, DFEP, MFEP, NESDA, NESDA_DG, RESP, TEACHER, roles_required,
                        visible_institutes, visible_sessions, visible_users, visible_wilayas)
from ..services import kpi as K
from ..services.period import Period, recent_years

bp = Blueprint("main", __name__)


def _period_ctx(period):
    return {"period": period, "years": recent_years(3), "families": K.KPI_FAMILIES, "icons": K.KPI_ICONS,
            "fmt": K.fmt, "RATES": K.RATES}


def _national_targets(period):
    """National target: sum of wilaya targets for counts, mean of wilaya targets for rates."""
    out, rates = {}, {}
    for o in Objective.query.filter_by(year=period.year, semester=period.semester, institute_id=None):
        if o.kpi in K.RATES:
            rates.setdefault(o.kpi, []).append(o.target)
        else:
            out[o.kpi] = out.get(o.kpi, 0) + o.target
    out.update({k: round(sum(v) / len(v), 1) for k, v in rates.items()})
    return out


@bp.route("/health")
def health():
    db.session.execute(db.text("SELECT 1"))
    return {"status": "ok"}


@bp.route("/")
def home():
    if current_user.is_authenticated and request.args.get("public") != "1":
        return redirect(url_for("main.dashboard"))
    open_sessions = (Session.query.filter_by(status="open").order_by(Session.starts_on).limit(6).all())
    return render_template("public/home.html", open_sessions=open_sessions)


@bp.route("/lang/<code>")
def set_lang(code):
    target = request.referrer or url_for("main.home")
    resp = redirect(target)
    if code in ("ar", "fr", "en"):
        resp.set_cookie("lang", code, max_age=3600 * 24 * 365, samesite="Lax")
        if current_user.is_authenticated:
            current_user.lang = code
            db.session.commit()
    return resp


@bp.route("/tableau-de-bord")
@login_required
def dashboard():
    u = current_user
    period = Period.from_request(request.args)
    ctx = _period_ctx(period)
    today = date.today()

    if u.role in (ADMIN, MFEP, NESDA_DG):
        wilayas = visible_wilayas(u).all()
        rows = K.wilaya_table(wilayas, period)
        values = K.finalize(K.merge(
            K.raw_by_institute([i.id for i in visible_institutes(u)], period.start, period.end).values()))
        tg = _national_targets(period)
        per = {k: K.kpi_status(k, values.get(k), tg.get(k), period) for k in K.KPIS}
        counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("met", "track", "late", "missed", "none")}
        ctx.update(view="nesda_dg" if u.role == NESDA_DG else "national", rows=rows, values=values,
                   targets=tg, per=per, counts=counts, n_wilayas=len(wilayas),
                   n_inst=sum(r["n_inst"] for r in rows))
        if u.role == NESDA_DG:
            ctx["pending"] = (Session.query.filter(Session.nesda_status.in_(("submitted", "wilaya_ok")))
                              .order_by(Session.nesda_submitted_at).all())
        return render_template("dashboard/national.html", **ctx)

    if u.role in (DFEP, COORD, NESDA):
        insts = visible_institutes(u).all()
        rows = K.institute_table(insts, period)
        values = K.finalize(K.merge(K.raw_by_institute([i.id for i in insts], period.start, period.end).values()))
        tg = K.targets(period, u.wilaya_id)
        per, status = K.evaluate(values, tg, period)
        sessions = visible_sessions(u)
        ctx.update(view="nesda" if u.role == NESDA else "wilaya", rows=rows, values=values, targets=tg,
                   per=per, status=status, wilaya=u.wilaya,
                   programme=Programme.query.filter_by(wilaya_id=u.wilaya_id, year=period.year).first(),
                   pending=sessions.filter(Session.nesda_status == "submitted").all(),
                   rejected=sessions.filter(Session.nesda_status == "rejected").all(),
                   reports_in=Report.query.filter_by(level="institute", wilaya_id=u.wilaya_id,
                                                     status="transmitted").count(),
                   running=sessions.filter(Session.status.in_(("open", "running"))).count())
        return render_template("dashboard/wilaya.html", **ctx)

    if u.role == RESP:
        inst = u.institute
        values = K.kpis_for_institutes([inst.id], period)
        tg = K.targets(period, inst.wilaya_id, inst.id)
        per, status = K.evaluate(values, tg, period)
        sessions = visible_sessions(u).order_by(Session.starts_on.desc()).all()
        ctx.update(view="institute", values=values, targets=tg, per=per, status=status, sessions=sessions,
                   to_close=[s for s in sessions if s.status == "running" and s.ends_on and s.ends_on < today],
                   to_submit=[s for s in sessions if s.status == "closed" and s.nesda_status in ("none", "rejected")],
                   to_print=[s for s in sessions if s.nesda_status == "validated"])
        return render_template("dashboard/institute.html", **ctx)

    # teacher
    my_slots = (Slot.query.filter(Slot.teacher_id == u.id).order_by(Slot.day, Slot.start).all())
    ctx.update(view="teacher",
               today_slots=[s for s in my_slots if s.day == today],
               upcoming=[s for s in my_slots if s.day > today][:8],
               missing=[s for s in my_slots if s.day < today and s.called_at is None][:8],
               modules=Module.query.filter_by(supervisor_id=u.id).all(),
               n_done=sum(1 for s in my_slots if s.called_at))
    return render_template("dashboard/teacher.html", **ctx)


@bp.route("/wilaya/<code>")
@roles_required(ADMIN, MFEP, NESDA_DG, DFEP, COORD, NESDA)
def wilaya_detail(code):
    w = Wilaya.query.filter_by(code=code).first_or_404()
    if w not in visible_wilayas(current_user).all():
        abort(403)
    period = Period.from_request(request.args)
    insts = [i for i in w.institutes if i.active]
    rows = K.institute_table(insts, period)
    values = K.finalize(K.merge(K.raw_by_institute([i.id for i in insts], period.start, period.end).values()))
    tg = K.targets(period, w.id)
    per, status = K.evaluate(values, tg, period)
    return render_template("dashboard/wilaya_detail.html", w=w, rows=rows, values=values, targets=tg, per=per,
                           status=status, **_period_ctx(period))


@bp.route("/comparaison")
@roles_required(ADMIN, MFEP, NESDA_DG)
def compare():
    period = Period.from_request(request.args)
    codes = [c for c in request.args.getlist("w") if c][:5]
    wilayas = Wilaya.query.filter(Wilaya.code.in_(codes)).order_by(Wilaya.code).all() if codes else []
    rows = K.wilaya_table(wilayas, period) if wilayas else []
    all_w = Wilaya.query.order_by(Wilaya.code).all()
    return render_template("dashboard/compare.html", rows=rows, all_wilayas=all_w, codes=codes,
                           **_period_ctx(period))


@bp.route("/integration")
@roles_required(ADMIN, MFEP)
def integration():
    return render_template("integration.html")
