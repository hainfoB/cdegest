import secrets
from collections import defaultdict
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from markupsafe import escape
from flask_login import current_user, login_required

from ..extensions import db
from ..i18n import t
from ..models import (AuditLog, Group, Institute, Objective, Programme, ProgrammeLine, Session, SurveyQuestion,
                      SurveyResponse, User, Wilaya, WorkshopTemplate)
from ..security import (ADMIN, CAN_CREATE, COORD, DFEP, MFEP, NEEDS_INSTITUTE, NEEDS_WILAYA, NESDA, NESDA_DG,
                        RESP, ROLES, TEACHER, roles_required, sees_people, visible_institutes, visible_sessions,
                        visible_users, visible_wilayas)
from ..services import kpi as K
from ..services.period import Period, recent_years, semester_bounds

bp = Blueprint("org", __name__)


def _int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _float(v):
    try:
        v = str(v).replace(",", ".").strip()
        return float(v) if v else None
    except ValueError:
        return None


def _date(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def gen_password():
    words = ["Atlas", "Sahara", "Tassili", "Hoggar", "Babor", "Aures", "Medjerda", "Chelia"]
    return f"{secrets.choice(words)}-{secrets.randbelow(9000) + 1000}-{secrets.token_urlsafe(4)}"


# ------------------------------------------------------------------ account

@bp.route("/compte", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        old, new, new2 = (request.form.get(k) or "" for k in ("old", "new", "new2"))
        if not current_user.check_password(old):
            flash(t("acc.bad_old"), "err")
        elif len(new) < 10 or new != new2:
            flash(t("acc.bad_new"), "err")
        else:
            current_user.set_password(new)
            current_user.must_change_password = False
            AuditLog.log("password.change", target=f"user:{current_user.id}")
            db.session.commit()
            flash(t("acc.changed"), "ok")
            return redirect(url_for("main.dashboard"))
    return render_template("org/account.html")


# ------------------------------------------------------------------ institutes

@bp.route("/instituts", methods=["GET", "POST"])
@roles_required(ADMIN, MFEP, DFEP, COORD, NESDA_DG, NESDA)
def institutes():
    can_edit = current_user.role in (ADMIN, DFEP, COORD)
    if request.method == "POST":
        if not can_edit:
            abort(403)
        f = request.form
        iid = _int(f.get("id"))
        inst = db.session.get(Institute, iid) if iid else None
        if inst and inst not in visible_institutes(current_user, include_inactive=True).all():
            abort(403)
        wil = current_user.wilaya if current_user.role != ADMIN else Wilaya.query.filter_by(code=f.get("wilaya")).first()
        code = (f.get("code") or "").strip().upper()[:30]
        if not (code and f.get("name_fr") and f.get("name_ar") and wil):
            flash(t("form.missing"), "err")
        elif Institute.query.filter(Institute.code == code, Institute.id != (iid or -1)).first():
            flash(t("inst.code_taken"), "err")
        else:
            inst = inst or Institute(wilaya=wil)
            inst.code, inst.kind = code, (f.get("kind") or "INSFP")[:10]
            inst.name_fr, inst.name_ar = f["name_fr"].strip()[:160], f["name_ar"].strip()[:160]
            inst.address, inst.phone = (f.get("address") or "")[:200], (f.get("phone") or "")[:30]
            inst.cde_opened_on = _date(f.get("cde_opened_on"))
            inst.active = f.get("active") == "1"
            db.session.add(inst)
            AuditLog.log("institute.save", target=f"institute:{code}")
            db.session.commit()
            flash(t("saved"), "ok")
        return redirect(url_for("org.institutes"))
    insts = visible_institutes(current_user, include_inactive=True).all()
    counts = defaultdict(int)
    for s in Session.query.filter(Session.institute_id.in_([i.id for i in insts] or [-1])):
        counts[s.institute_id] += 1
    staff = defaultdict(int)
    for u in User.query.filter(User.institute_id.in_([i.id for i in insts] or [-1]), User.active.is_(True)):
        staff[u.institute_id] += 1
    edit = db.session.get(Institute, _int(request.args.get("edit"), -1))
    return render_template("org/institutes.html", insts=insts, counts=counts, staff=staff, can_edit=can_edit,
                           edit=edit if edit in insts else None, wilayas=visible_wilayas(current_user).all())


# ------------------------------------------------------------------ accounts

def _can_manage(me, u):
    return (u.id != me.id and u.role in CAN_CREATE.get(me.role, set())
            and visible_users(me).filter(User.id == u.id).count() == 1)


@bp.route("/comptes", methods=["GET", "POST"])
@roles_required(ADMIN, MFEP, DFEP, COORD, RESP, NESDA_DG)
def users():
    me = current_user
    creatable = [r for r in ROLES if r in CAN_CREATE.get(me.role, set())]
    if request.method == "POST":
        f = request.form
        action = f.get("action", "create")
        if action == "create":
            role = f.get("role")
            email = (f.get("email") or "").strip().lower()
            if role not in creatable or not email or not f.get("name"):
                flash(t("form.missing"), "err")
                return redirect(url_for("org.users"))
            if User.query.filter_by(email=email).first():
                flash(t("users.email_taken"), "err")
                return redirect(url_for("org.users"))
            u = User(name=f["name"].strip()[:120], email=email, phone=(f.get("phone") or "")[:30], role=role,
                     lang=f.get("lang") if f.get("lang") in ("ar", "fr", "en") else "ar")
            if role in NEEDS_INSTITUTE:
                inst = db.session.get(Institute, _int(f.get("institute"), -1))
                if inst not in visible_institutes(me).all():
                    flash(t("form.missing"), "err")
                    return redirect(url_for("org.users"))
                u.institute, u.wilaya = inst, inst.wilaya
            elif role in NEEDS_WILAYA:
                w = me.wilaya if me.role in (DFEP, COORD) else Wilaya.query.filter_by(code=f.get("wilaya")).first()
                if w is None or w not in visible_wilayas(me).all():
                    flash(t("form.missing"), "err")
                    return redirect(url_for("org.users"))
                u.wilaya = w
            pwd = gen_password()
            u.set_password(pwd)
            u.must_change_password = True
            db.session.add(u)
            AuditLog.log("user.create", target=email, details=role)
            db.session.commit()
            flash(t("users.created", email=escape(email), pwd=pwd), "pwd")
        else:
            u = db.session.get(User, _int(f.get("id"), -1))
            if not u or not _can_manage(me, u):
                abort(403)
            if action == "toggle":
                u.active = not u.active
                AuditLog.log("user.toggle", target=u.email, details=str(u.active))
                flash(t("saved"), "ok")
            elif action == "reset":
                pwd = gen_password()
                u.set_password(pwd)
                u.must_change_password = True
                AuditLog.log("user.reset", target=u.email)
                flash(t("users.reset_done", email=escape(u.email), pwd=pwd), "pwd")
            db.session.commit()
        return redirect(url_for("org.users"))
    rows = visible_users(me).order_by(User.role, User.name).all()
    return render_template("org/users.html", rows=rows, creatable=creatable,
                           institutes=visible_institutes(me).all(), wilayas=visible_wilayas(me).all(),
                           can_manage=lambda u: _can_manage(me, u), NEEDS_INSTITUTE=NEEDS_INSTITUTE,
                           NEEDS_WILAYA=NEEDS_WILAYA)


# ------------------------------------------------------------------ référentiel

@bp.route("/referentiel", methods=["GET", "POST"])
@roles_required(ADMIN, MFEP, DFEP, COORD, RESP)
def referentiel():
    can_edit = current_user.role in (ADMIN, MFEP)
    if request.method == "POST":
        if not can_edit:
            abort(403)
        f = request.form
        tpl = db.session.get(WorkshopTemplate, _int(f.get("id"), -1)) or WorkshopTemplate()
        code = (f.get("code") or "").strip().upper()[:20]
        if not (code and f.get("title_fr") and f.get("title_ar")):
            flash(t("form.missing"), "err")
            return redirect(url_for("org.referentiel"))
        if WorkshopTemplate.query.filter(WorkshopTemplate.code == code, WorkshopTemplate.id != (tpl.id or -1)).first():
            flash(t("inst.code_taken"), "err")
            return redirect(url_for("org.referentiel"))
        tpl.code, tpl.theme, tpl.kind = code, (f.get("theme") or "")[:60], f.get("kind") or "atelier"
        tpl.title_fr, tpl.title_ar = f["title_fr"][:160], f["title_ar"][:160]
        tpl.objectives_fr, tpl.objectives_ar = f.get("objectives_fr"), f.get("objectives_ar")
        tpl.hours = _int(f.get("hours"), 12)
        tpl.active = f.get("active") == "1"
        db.session.add(tpl)
        AuditLog.log("referentiel.save", target=code)
        db.session.commit()
        flash(t("saved"), "ok")
        return redirect(url_for("org.referentiel"))
    tpls = WorkshopTemplate.query.order_by(WorkshopTemplate.theme, WorkshopTemplate.code).all()
    used = defaultdict(int)
    for s in visible_sessions(current_user) if current_user.role != MFEP else Session.query:
        used[s.template_id] += 1
    edit = db.session.get(WorkshopTemplate, _int(request.args.get("edit"), -1))
    return render_template("org/referentiel.html", tpls=tpls, can_edit=can_edit, used=used, edit=edit)


# ------------------------------------------------------------------ objectives

@bp.route("/objectifs", methods=["GET", "POST"])
@roles_required(ADMIN, MFEP, DFEP, COORD, RESP)
def objectives():
    me = current_user
    year = request.values.get("y") or Period().year
    if me.role in (ADMIN, MFEP):
        w = Wilaya.query.filter_by(code=request.values.get("w") or "34").first_or_404()
    else:
        w = me.scope_wilaya
    insts = [i for i in w.institutes if i.active]
    if me.role == RESP:
        insts = [me.institute]
    sel_inst = None
    iid = _int(request.values.get("i"))
    if iid:
        sel_inst = next((i for i in insts if i.id == iid), None)
    if me.role == RESP:
        sel_inst = me.institute
    can_edit_w = me.role in (ADMIN, MFEP)
    can_edit_i = me.role in (ADMIN, DFEP, COORD)

    if request.method == "POST":
        level_inst = sel_inst
        if (level_inst is None and not can_edit_w) or (level_inst is not None and not can_edit_i):
            abort(403)
        if request.form.get("action") == "copy_all" and can_edit_w:
            src = Objective.query.filter_by(year=year, wilaya_id=w.id, institute_id=None).all()
            n = 0
            for other in Wilaya.query.filter(Wilaya.id != w.id):
                if Objective.query.filter_by(year=year, wilaya_id=other.id, institute_id=None).first():
                    continue
                for o in src:
                    db.session.add(Objective(year=year, semester=o.semester, wilaya_id=other.id, kpi=o.kpi,
                                             target=o.target, set_by_id=me.id))
                n += 1
            AuditLog.log("objectives.copy", target=f"wilaya:{w.code}", details=f"{year} -> {n} wilayas")
            db.session.commit()
            flash(t("obj.copied", n=n), "ok")
            return redirect(url_for("org.objectives", y=year, w=w.code))
        for kpi in K.KPIS:
            for sem in (1, 2, 0):
                val = _float(request.form.get(f"{kpi}_{sem}"))
                o = Objective.query.filter_by(year=year, semester=sem, wilaya_id=w.id,
                                              institute_id=level_inst.id if level_inst else None, kpi=kpi).first()
                if val is None:
                    if o:
                        db.session.delete(o)
                    continue
                if o is None:
                    o = Objective(year=year, semester=sem, wilaya_id=w.id,
                                  institute_id=level_inst.id if level_inst else None, kpi=kpi)
                    db.session.add(o)
                o.target, o.set_by_id = val, me.id
        AuditLog.log("objectives.save", target=f"wilaya:{w.code}",
                     details=f"{year} {level_inst.code if level_inst else 'wilaya'}")
        db.session.commit()
        flash(t("saved"), "ok")
        return redirect(url_for("org.objectives", y=year, w=w.code, i=sel_inst.id if sel_inst else None))

    def grid(inst_id):
        g = {}
        for o in Objective.query.filter_by(year=year, wilaya_id=w.id, institute_id=inst_id):
            g[(o.kpi, o.semester)] = o.target
        return g

    wgrid = grid(None)
    igrid = grid(sel_inst.id) if sel_inst else {}
    # distribution check: sum of institute targets vs wilaya target (counts only)
    sums = defaultdict(float)
    for o in Objective.query.filter(Objective.year == year, Objective.wilaya_id == w.id,
                                    Objective.institute_id.isnot(None)):
        sums[(o.kpi, o.semester)] += o.target
    return render_template("org/objectives.html", w=w, year=year, years=recent_years(3) + [_next_year(year)],
                           insts=insts, sel_inst=sel_inst, wgrid=wgrid, igrid=igrid, sums=sums,
                           can_edit_w=can_edit_w, can_edit_i=can_edit_i, KPIS=K.KPIS, RATES=K.RATES,
                           wilayas=Wilaya.query.order_by(Wilaya.code).all(), families=K.KPI_FAMILIES)


def _next_year(label):
    y = int(label[:4]) + 1
    return f"{y}-{y + 1}"


# ------------------------------------------------------------------ programme annuel

@bp.route("/programme", methods=["GET", "POST"])
@roles_required(ADMIN, DFEP, COORD, RESP)
def programme():
    me = current_user
    year = request.values.get("y") or Period().year
    if me.role == ADMIN:
        w = Wilaya.query.filter_by(code=request.values.get("w") or "34").first_or_404()
    else:
        w = me.scope_wilaya
    prog = Programme.query.filter_by(wilaya_id=w.id, year=year).first()
    can_edit = me.role in (ADMIN, DFEP, COORD) and (prog is None or prog.status in ("draft", "returned"))
    can_validate = me.role in (ADMIN, DFEP)

    if request.method == "POST":
        action = request.form.get("action")
        if prog is None:
            if me.role not in (ADMIN, DFEP, COORD):
                abort(403)
            prog = Programme(wilaya_id=w.id, year=year)
            db.session.add(prog)
            db.session.flush()
        if action == "add_line" and can_edit:
            inst = db.session.get(Institute, _int(request.form.get("institute"), -1))
            tpl = db.session.get(WorkshopTemplate, _int(request.form.get("template"), -1))
            if inst and tpl and inst.wilaya_id == w.id:
                db.session.add(ProgrammeLine(programme=prog, institute=inst, template=tpl,
                                             semester=1 if request.form.get("semester") == "1" else 2,
                                             planned_groups=max(1, _int(request.form.get("groups"), 1))))
        elif action == "del_line" and can_edit:
            line = db.session.get(ProgrammeLine, _int(request.form.get("line"), -1))
            if line and line.programme_id == prog.id:
                db.session.delete(line)
        elif action == "submit" and me.role in (ADMIN, DFEP, COORD) and prog.status in ("draft", "returned"):
            prog.status = "submitted"
            AuditLog.log("programme.submit", target=f"wilaya:{w.code}", details=year)
        elif action == "validate" and can_validate and prog.status == "submitted":
            prog.status, prog.validated_by_id, prog.validated_at = "validated", me.id, db.func.now()
            AuditLog.log("programme.validate", target=f"wilaya:{w.code}", details=year)
        elif action == "return" and can_validate and prog.status in ("submitted", "validated"):
            prog.status, prog.note = "returned", (request.form.get("note") or "")[:1000]
            AuditLog.log("programme.return", target=f"wilaya:{w.code}", details=year)
        else:
            abort(403)
        db.session.commit()
        flash(t("saved"), "ok")
        return redirect(url_for("org.programme", y=year, w=w.code))

    lines = prog.lines if prog else []
    if me.role == RESP:
        lines = [l for l in lines if l.institute_id == me.institute_id]
    # realised groups for each line (sessions of the same template in the same institute and semester)
    realised = {}
    for l in lines:
        a, b = semester_bounds(year, l.semester)
        realised[l.id] = (Group.query.join(Session, Group.session_id == Session.id)
                          .filter(Session.template_id == l.template_id, Session.institute_id == l.institute_id,
                                  Session.starts_on.between(a, b), Session.status != "draft").count())
    return render_template("org/programme.html", w=w, year=year, years=recent_years(3) + [_next_year(year)],
                           prog=prog, lines=lines, realised=realised, can_edit=can_edit,
                           can_validate=can_validate, insts=[i for i in w.institutes if i.active],
                           tpls=WorkshopTemplate.query.filter_by(active=True).order_by(WorkshopTemplate.code).all(),
                           wilayas=Wilaya.query.order_by(Wilaya.code).all())


# ------------------------------------------------------------------ satisfaction

@bp.route("/satisfaction", methods=["GET", "POST"])
@roles_required(ADMIN, MFEP, DFEP, COORD, RESP, NESDA_DG)
def surveys():
    me = current_user
    can_edit = me.role in (ADMIN, MFEP)
    if request.method == "POST":
        if not can_edit:
            abort(403)
        f = request.form
        q = db.session.get(SurveyQuestion, _int(f.get("id"), -1)) or SurveyQuestion()
        if not (f.get("text_fr") and f.get("text_ar") and f.get("text_en")):
            flash(t("form.missing"), "err")
        else:
            q.text_fr, q.text_ar, q.text_en = f["text_fr"][:200], f["text_ar"][:200], f["text_en"][:200]
            q.order = _int(f.get("order"), 0)
            q.active = f.get("active") == "1"
            q.is_overall = f.get("is_overall") == "1"
            if q.is_overall:
                SurveyQuestion.query.filter(SurveyQuestion.id != (q.id or -1)).update({"is_overall": False})
            db.session.add(q)
            AuditLog.log("survey.question", target=f"q:{q.order}")
            db.session.commit()
            flash(t("saved"), "ok")
        return redirect(url_for("org.surveys"))
    questions = SurveyQuestion.query.order_by(SurveyQuestion.order).all()
    period = Period.from_request(request.args)
    if me.role in (ADMIN, MFEP, NESDA_DG):
        inst_ids = [i.id for i in visible_institutes(me)]
    else:
        inst_ids = [i.id for i in visible_institutes(me)]
    resp = (SurveyResponse.query.join(Session, SurveyResponse.session_id == Session.id)
            .filter(Session.institute_id.in_(inst_ids or [-1])).all())
    resp = [r for r in resp if period.start <= r.created_at.date() <= period.end]
    by_session = defaultdict(list)
    for r in resp:
        by_session[r.session_id].append(r)
    stats = []
    for sid, rs in by_session.items():
        s = db.session.get(Session, sid)
        avg = {}
        for q in questions:
            vals = [r.answers_dict().get(q.id) for r in rs if r.answers_dict().get(q.id)]
            avg[q.id] = round(sum(vals) / len(vals), 1) if vals else None
        sat = round(100 * sum(1 for r in rs if (r.overall or 0) >= 4) / len(rs))
        comments = [r.comment for r in rs if r.comment] if sees_people(me) else []
        stats.append({"session": s, "n": len(rs), "avg": avg, "sat": sat, "comments": comments})
    stats.sort(key=lambda x: (x["session"].institute.wilaya.code, x["session"].starts_on or date.min))
    edit = db.session.get(SurveyQuestion, _int(request.args.get("edit"), -1))
    return render_template("org/surveys.html", questions=questions, stats=stats, can_edit=can_edit, edit=edit,
                           period=period, years=recent_years(3), show_names=me.role != MFEP)


# ------------------------------------------------------------------ journal

@bp.route("/journal")
@roles_required(ADMIN, MFEP, DFEP, COORD, RESP, NESDA_DG)
def audit():
    me = current_user
    q = AuditLog.query
    if me.role == MFEP:
        q = q.join(User, AuditLog.user_id == User.id).filter(User.role == MFEP)
    elif me.role == NESDA_DG:
        q = q.join(User, AuditLog.user_id == User.id).filter(User.role.in_((NESDA_DG, NESDA)))
    elif me.role in (DFEP, COORD):
        q = q.filter(AuditLog.wilaya_id == me.wilaya_id)
    elif me.role == RESP:
        q = q.filter(AuditLog.institute_id == me.institute_id)
    page = max(1, _int(request.args.get("page"), 1))
    rows = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * 50).limit(51).all()
    return render_template("org/audit.html", rows=rows[:50], page=page, has_next=len(rows) > 50)
