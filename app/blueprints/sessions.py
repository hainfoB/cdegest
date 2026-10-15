import io
from datetime import date, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..i18n import t
from ..models import (AuditLog, Enrollment, Group, Institute, Module, Participant, Session, Slot, User,
                      WorkshopTemplate)
from ..security import (ADMIN, CERT_PRINTERS, RESP, TEACHER, can_manage_session, can_see_session,
                        roles_required, visible_institutes, visible_sessions)
from ..services import training as T
from ..utils import utcnow

bp = Blueprint("sessions", __name__)

STATUSES = ("draft", "open", "running", "closed")


def _int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _date(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def _hm(v):
    v = (v or "").strip()
    if len(v) == 5 and v[2] == ":" and v[:2].isdigit() and v[3:].isdigit() and int(v[:2]) < 24 and int(v[3:]) < 60:
        return v
    return None


def get_session(sid):
    s = db.session.get(Session, sid)
    if s is None:
        abort(404)
    if not can_see_session(current_user, s):
        abort(403)
    return s


def require_manage(s):
    if not can_manage_session(current_user, s):
        abort(403)


def teachers_of(inst_id):
    return (User.query.filter_by(institute_id=inst_id, role=TEACHER, active=True).order_by(User.name).all())


# ------------------------------------------------------------------ list / create

@bp.route("/sessions")
@roles_required(ADMIN, "dfep", "coord", RESP, TEACHER)
def index():
    st = request.args.get("st")
    q = visible_sessions(current_user)
    if st in STATUSES:
        q = q.filter(Session.status == st)
    rows = q.order_by(Session.starts_on.desc()).all()
    return render_template("sessions/index.html", rows=rows, st=st, statuses=STATUSES,
                           can_create=current_user.role in (ADMIN, RESP))


@bp.route("/sessions/nouvelle", methods=["GET", "POST"])
@roles_required(ADMIN, RESP)
def create():
    insts = visible_institutes(current_user).all()
    tpls = WorkshopTemplate.query.filter_by(active=True).order_by(WorkshopTemplate.code).all()
    if request.method == "POST":
        f = request.form
        inst = current_user.institute if current_user.role == RESP else db.session.get(Institute, _int(f.get("institute"), -1))
        tpl = db.session.get(WorkshopTemplate, _int(f.get("template"), -1))
        a, b = _date(f.get("starts_on")), _date(f.get("ends_on"))
        if not (inst and tpl and a and b and a <= b):
            flash(t("form.missing"), "err")
        else:
            s = Session(institute=inst, template=tpl, created_by_id=current_user.id)
            _apply(s, f, tpl)
            db.session.add(s)
            db.session.flush()
            db.session.add(Group(session=s, name="G1"))
            AuditLog.log("session.create", target=f"session:{s.id}", details=s.title)
            db.session.commit()
            flash(t("sess.created"), "ok")
            return redirect(url_for("sessions.view", sid=s.id, tab="modules"))
    return render_template("sessions/form.html", s=None, insts=insts, tpls=tpls)


def _apply(s, f, tpl=None):
    s.title = (f.get("title") or (tpl.title_fr if tpl else "") or "Session")[:160]
    s.description = f.get("description")
    s.mode = f.get("mode") if f.get("mode") in ("onsite", "online", "hybrid") else "onsite"
    s.location = (f.get("location") or "")[:200]
    s.online_url = (f.get("online_url") or "")[:300]
    s.starts_on, s.ends_on = _date(f.get("starts_on")), _date(f.get("ends_on"))
    s.seats_per_group = max(1, _int(f.get("seats_per_group"), 20))
    s.min_attendance = min(100, max(0, _int(f.get("min_attendance"), 80)))
    s.auto_confirm = f.get("auto_confirm") == "1"


# ------------------------------------------------------------------ session page

@bp.route("/sessions/<int:sid>")
@login_required
def view(sid):
    s = get_session(sid)
    tab = request.args.get("tab", "apercu")
    manage = can_manage_session(current_user, s)
    ctx = {"s": s, "tab": tab, "manage": manage, "today": date.today(),
           "can_print": current_user.role in CERT_PRINTERS and s.certificates_open}
    if tab == "modules" or tab == "planning":
        ctx["teachers"] = teachers_of(s.institute_id)
    if tab in ("inscrits", "presence", "attestations"):
        enrs = sorted(s.enrollments, key=lambda e: (e.group.name if e.group else "~", e.participant.last_name))
        if current_user.role == TEACHER:
            my_groups = {sl.group_id for g in s.groups for sl in g.slots if sl.teacher_id == current_user.id}
            sup = any(m.supervisor_id == current_user.id for m in s.modules)
            if not sup:
                enrs = [e for e in enrs if e.group_id in my_groups]
        ctx["enrs"] = enrs
        ctx["stats"] = {e.id: T.enrollment_stats(e) for e in enrs}
        ctx["elig"] = {e.id: T.eligible(e, ctx["stats"][e.id]) for e in enrs}
    if tab == "presence":
        gid = _int(request.args.get("g")) or (s.groups[0].id if s.groups else None)
        ctx["group"] = next((g for g in s.groups if g.id == gid), None)
    return render_template("sessions/view.html", **ctx)


@bp.route("/sessions/<int:sid>/modifier", methods=["POST"])
@login_required
def edit(sid):
    s = get_session(sid)
    require_manage(s)
    _apply(s, request.form, s.template)
    AuditLog.log("session.edit", target=f"session:{s.id}")
    db.session.commit()
    flash(t("saved"), "ok")
    return redirect(url_for("sessions.view", sid=s.id))


@bp.route("/sessions/<int:sid>/action", methods=["POST"])
@login_required
def action(sid):
    s = get_session(sid)
    act = request.form.get("action")
    flashed = False
    if act == "submit_nesda":
        require_manage(s)
        ok = T.nesda_submit(s, current_user)
    else:
        require_manage(s)
        ok = True
        if act == "open":
            ok = s.status == "draft" and s.modules and s.groups and any(g.slots for g in s.groups)
            if ok:
                s.status = "open"
            else:
                flash(t("sess.cannot_open"), "err")
                flashed = True
        elif act == "start" and s.status == "open":
            s.status = "running"
        elif act == "reopen_reg" and s.status == "running":
            s.status = "open"
        elif act == "close" and s.status in ("open", "running"):
            T.close_session(s, current_user)
        elif act == "dropouts" and s.status in ("open", "running"):
            n = T.detect_dropouts(s, user=current_user)
            flash(t("sess.dropouts_found", n=n), "ok")
        elif act == "delete" and s.status == "draft" and not s.enrollments:
            AuditLog.log("session.delete", target=f"session:{s.id}", details=s.title)
            db.session.delete(s)
            db.session.commit()
            flash(t("saved"), "ok")
            return redirect(url_for("sessions.index"))
        else:
            ok = False
    if ok:
        AuditLog.log(f"session.{act}", target=f"session:{s.id}")
        db.session.commit()
        if act != "dropouts":
            flash(t("saved"), "ok")
    elif not flashed:
        flash(t("sess.action_refused"), "err")
    return redirect(url_for("sessions.view", sid=s.id, tab=request.form.get("tab") or "apercu"))


# ------------------------------------------------------------------ modules, groups, slots

@bp.route("/sessions/<int:sid>/modules", methods=["POST"])
@login_required
def modules(sid):
    s = get_session(sid)
    require_manage(s)
    f = request.form
    if f.get("action") == "delete":
        m = db.session.get(Module, _int(f.get("id"), -1))
        if m and m.session_id == s.id:
            if Slot.query.filter_by(module_id=m.id).count():
                flash(t("mod.in_use"), "err")
            else:
                db.session.delete(m)
    else:
        sup = db.session.get(User, _int(f.get("supervisor"), -1))
        if not f.get("title") or not sup or sup.role != TEACHER or sup.institute_id != s.institute_id:
            flash(t("form.missing"), "err")
            return redirect(url_for("sessions.view", sid=s.id, tab="modules"))
        m = db.session.get(Module, _int(f.get("id"), -1)) if f.get("id") else None
        if m is None or m.session_id != s.id:
            m = Module(session=s, order=len(s.modules) + 1)
            db.session.add(m)
        m.title, m.hours, m.supervisor = f["title"][:160], max(1, _int(f.get("hours"), 3)), sup
    AuditLog.log("session.modules", target=f"session:{s.id}")
    db.session.commit()
    return redirect(url_for("sessions.view", sid=s.id, tab="modules"))


@bp.route("/sessions/<int:sid>/groupes", methods=["POST"])
@login_required
def groups(sid):
    s = get_session(sid)
    require_manage(s)
    f = request.form
    if f.get("action") == "delete":
        g = db.session.get(Group, _int(f.get("id"), -1))
        if g and g.session_id == s.id and not g.enrollments and len(s.groups) > 1:
            db.session.delete(g)
        else:
            flash(t("grp.in_use"), "err")
    else:
        name = (f.get("name") or f"G{len(s.groups) + 1}")[:30]
        db.session.add(Group(session=s, name=name, room=(f.get("room") or "")[:80]))
    db.session.commit()
    return redirect(url_for("sessions.view", sid=s.id, tab="planning"))


@bp.route("/sessions/<int:sid>/creneaux", methods=["POST"])
@login_required
def slots(sid):
    s = get_session(sid)
    require_manage(s)
    f = request.form
    if f.get("action") in ("cancel", "restore"):
        sl = db.session.get(Slot, _int(f.get("id"), -1))
        if not sl or sl.group.session_id != s.id:
            abort(404)
        if f["action"] == "cancel" and not sl.attendances:
            sl.cancelled, sl.cancel_reason, sl.cancelled_by_id = True, (f.get("reason") or "enseignant_absent")[:20], current_user.id
            AuditLog.log("slot.cancel", target=f"slot:{sl.id}", details=sl.cancel_reason)
            flash(t("slot.cancelled_ok"), "ok")
        elif f["action"] == "restore":
            sl.cancelled, sl.cancel_reason = False, None
            AuditLog.log("slot.restore", target=f"slot:{sl.id}")
        else:
            flash(t("slot.in_use"), "err")
        db.session.commit()
        return redirect(url_for("sessions.view", sid=s.id, tab="planning"))
    if f.get("action") == "delete":
        sl = db.session.get(Slot, _int(f.get("id"), -1))
        if sl and sl.group.session_id == s.id and not sl.attendances:
            db.session.delete(sl)
            db.session.commit()
        else:
            flash(t("slot.in_use"), "err")
        return redirect(url_for("sessions.view", sid=s.id, tab="planning"))
    mod = db.session.get(Module, _int(f.get("module"), -1))
    teacher = db.session.get(User, _int(f.get("teacher"), -1))
    day, start, end = _date(f.get("day")), _hm(f.get("start")), _hm(f.get("end"))
    gids = {_int(x) for x in f.getlist("groups")}
    groups_sel = [g for g in s.groups if g.id in gids]
    repeat = min(20, max(1, _int(f.get("repeat"), 1)))
    if not (mod and mod.session_id == s.id and teacher and day and start and end and start < end and groups_sel):
        flash(t("form.missing"), "err")
        return redirect(url_for("sessions.view", sid=s.id, tab="planning"))
    # rule: every teacher of the session supervises at least one module
    if not any(m.supervisor_id == teacher.id for m in s.modules):
        flash(t("slot.teacher_needs_module", name=teacher.name), "err")
        return redirect(url_for("sessions.view", sid=s.id, tab="planning"))
    n = 0
    for k in range(repeat):
        d = day + timedelta(days=7 * k)
        for g in groups_sel:
            db.session.add(Slot(group=g, module=mod, teacher=teacher, day=d, start=start, end=end))
            n += 1
    AuditLog.log("session.slots", target=f"session:{s.id}", details=f"+{n}")
    db.session.commit()
    flash(t("slot.added", n=n), "ok")
    return redirect(url_for("sessions.view", sid=s.id, tab="planning"))


# ------------------------------------------------------------------ enrolments

@bp.route("/sessions/<int:sid>/inscriptions", methods=["POST"])
@login_required
def enrollments(sid):
    s = get_session(sid)
    require_manage(s)
    f = request.form
    act = f.get("action")
    if act == "add":
        if not (f.get("last_name") and f.get("first_name") and f.get("phone")):
            flash(t("form.missing"), "err")
            return redirect(url_for("sessions.view", sid=s.id, tab="inscrits"))
        p = Participant.query.filter_by(phone=f["phone"].strip()).first() or Participant()
        p.last_name, p.first_name = f["last_name"].strip()[:80], f["first_name"].strip()[:80]
        p.phone, p.email = f["phone"].strip()[:30], (f.get("email") or "").strip()[:150] or None
        p.sex = f.get("sex") if f.get("sex") in ("F", "M") else None
        p.status = "diplome" if f.get("pstatus") == "diplome" else "stagiaire"
        p.specialty = (f.get("specialty") or "")[:120]
        p.wilaya_id = p.wilaya_id or s.institute.wilaya_id
        p.consent_at = p.consent_at or utcnow()
        db.session.add(p)
        db.session.flush()
        if Enrollment.query.filter_by(session_id=s.id, participant_id=p.id).first():
            flash(t("enr.already"), "err")
        else:
            e = Enrollment(session=s, participant=p, source="cde")
            db.session.add(e)
            T.place_enrollment(e)
            AuditLog.log("enrollment.add", target=f"session:{s.id}")
        db.session.commit()
        return redirect(url_for("sessions.view", sid=s.id, tab="inscrits"))
    e = db.session.get(Enrollment, _int(f.get("id"), -1))
    if not e or e.session_id != s.id:
        abort(404)
    if act == "confirm":
        if not e.group:
            T.place_enrollment(e)
        if e.group:
            e.status = "confirmed"
    elif act == "cancel":
        e.status = "cancelled"
    elif act == "desist":
        e.dropout, e.dropout_on, e.dropout_reason = True, date.today(), "desistement"
    elif act == "undrop":
        e.dropout, e.dropout_on, e.dropout_reason = False, None, None
    elif act == "group":
        g = next((g for g in s.groups if g.id == _int(f.get("group"))), None)
        if g:
            e.group = g
    AuditLog.log(f"enrollment.{act}", target=f"enrollment:{e.id}")
    db.session.commit()
    return redirect(url_for("sessions.view", sid=s.id, tab="inscrits"))


# ------------------------------------------------------------------ roll call

def _can_call(slot):
    """Teacher: own slot, same day. CDE manager: any time (recorded as a correction afterwards)."""
    s = slot.group.session
    if can_manage_session(current_user, s):
        return "manage"
    if current_user.role == TEACHER and slot.teacher_id == current_user.id:
        return "teacher" if slot.day == date.today() else "locked"
    return None


@bp.route("/appel/<int:slot_id>", methods=["GET", "POST"])
@login_required
def roll_call(slot_id):
    slot = db.session.get(Slot, slot_id) or abort(404)
    mode = _can_call(slot)
    if slot.cancelled and mode == "teacher":
        mode = "locked"
    s = slot.group.session
    if mode is None and not can_see_session(current_user, s):
        abort(403)
    enrs = sorted([e for e in slot.group.enrollments if e.status == "confirmed"],
                  key=lambda e: (e.participant.last_name, e.participant.first_name))
    marks = {a.enrollment_id: a for a in slot.attendances}
    if request.method == "POST":
        if mode not in ("teacher", "manage"):
            abort(403)
        correction = mode == "manage" and (slot.day < date.today() or slot.called_at is not None)
        for e in enrs:
            st = request.form.get(f"st_{e.id}")
            if st not in ("present", "late", "absent", "excused"):
                continue
            prev = marks.get(e.id)
            arr, lef = _hm(request.form.get(f"in_{e.id}")), _hm(request.form.get(f"out_{e.id}"))
            if prev and prev.status == st and prev.arrived == arr and prev.left == lef:
                continue
            T.mark(slot, e, st, current_user, arrived=arr, left=lef, correction=correction)
        slot.called_at = slot.called_at or utcnow()
        AuditLog.log("attendance.correction" if correction else "attendance.call", target=f"slot:{slot.id}")
        db.session.commit()
        flash(t("call.saved"), "ok")
        nxt = request.form.get("next")
        return redirect(nxt if nxt and nxt.startswith("/") else url_for("sessions.roll_call", slot_id=slot.id))
    return render_template("sessions/roll_call.html", slot=slot, s=s, enrs=enrs, marks=marks, mode=mode)


@bp.route("/mes-creneaux")
@roles_required(TEACHER)
def my_slots():
    rows = Slot.query.filter_by(teacher_id=current_user.id).order_by(Slot.day.desc(), Slot.start).all()
    return render_template("sessions/my_slots.html", rows=rows, today=date.today())


# ------------------------------------------------------------------ certificates & export

@bp.route("/sessions/<int:sid>/attestations")
@login_required
def certificates(sid):
    s = get_session(sid)
    if current_user.role not in CERT_PRINTERS or not s.certificates_open:
        abort(403)
    one = _int(request.args.get("e"))
    enrs = [e for e in s.enrollments if e.cert_no and (one is None or e.id == one)]
    enrs.sort(key=lambda e: e.participant.last_name)
    AuditLog.log("certificates.print", target=f"session:{s.id}", details=str(len(enrs)))
    db.session.commit()
    return render_template("certificate.html", items=[(e, T.enrollment_stats(e)) for e in enrs], s=s)


@bp.route("/sessions/<int:sid>/export.xlsx")
@login_required
def export(sid):
    from ..services import xl
    s = get_session(sid)
    wb = xl.book()
    ws = xl.sheet(wb, t("xl.participants"), first=True)
    ws.append([t(k) for k in ("xl.group", "pub.last_name", "pub.first_name", "pub.sex", "pub.phone", "enr.status",
                              "xl.present", "xl.slots", "kpi.attendance", "xl.dropout", "xl.eligible", "xl.cert_no",
                              "nesda.status")])
    xl.header(ws)
    for e in sorted(s.enrollments, key=lambda e: (e.group.name if e.group else "~", e.participant.last_name)):
        st = T.enrollment_stats(e)
        p = e.participant
        ws.append([e.group.name if e.group else "", p.last_name, p.first_name, t("sex." + p.sex) if p.sex else "",
                   p.phone or "", t("enr.st." + e.status), st["present"], st["expected"], st["rate"],
                   t("drop." + e.dropout_reason) if e.dropout_reason else "",
                   t("yes") if T.eligible(e, st) else t("no"), e.cert_no or "", t("ns." + p.nesda_status)])
    xl.widths(ws, 8, 20, 18, 8, 14, 13, 10, 9, 11, 13, 9, 20, 14)
    AuditLog.log("session.export", target=f"session:{s.id}")
    db.session.commit()
    return xl.send(wb, f"session-{s.id}.xlsx")
