import secrets
from collections import defaultdict
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from markupsafe import escape
from flask_login import current_user, login_required

from ..extensions import db
from ..i18n import get_lang, t
from .. import nin as NIN
from ..models import (AuditLog, Group, Habilitation, Institute, Objective, Programme, ProgrammeLine, Session, SurveyQuestion,
                      SurveyResponse, User, Wilaya, WorkshopTemplate)
from ..utils import utcnow
from ..security import (ADMIN, CAN_CREATE, COORD, DFEP, MFEP, NEEDS_INSTITUTE, NEEDS_WILAYA, NESDA, NESDA_DG,
                        RESP, ROLES, TEACHER, roles_required, sees_people, visible_habilitations, visible_institutes,
                        visible_sessions, visible_users, visible_wilayas)
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
    """Mon compte : mot de passe, canaux de contact, préférences de messages, mes rôles (US-107, US-109, US-1105)."""
    me = current_user
    if request.method == "POST":
        sect = request.form.get("section", "password")
        if sect == "password":
            old, new, new2 = (request.form.get(k) or "" for k in ("old", "new", "new2"))
            minlen = 12 if me.agent_habilitations() else 10
            if not me.check_password(old):
                flash(t("acc.bad_old"), "err")
            elif len(new) < minlen or new != new2:
                flash(t("acc.bad_new"), "err")
            else:
                me.set_password(new)
                me.must_change_password = False
                AuditLog.log("password.change", target=f"user:{me.id}")
                from ..services.events import security_alert
                security_alert(me, "password")
                db.session.commit()
                flash(t("acc.changed"), "ok")
                return redirect(url_for("main.dashboard") if me.is_agent else url_for("espace.home"))
        elif sect == "contact":
            f = request.form
            email = (f.get("email") or "").strip().lower()[:150]
            phone = "".join(c for c in (f.get("phone") or "") if c.isdigit() or c == "+")[:20]
            wa = "".join(c for c in (f.get("whatsapp") or "") if c.isdigit() or c == "+")[:20]
            changed = (email != (me.email or "")) or (phone != (me.phone or "")) or (wa != (me.whatsapp or ""))
            if changed:
                from ..services.events import security_alert
                security_alert(me, "channel")             # alerte envoyée à l'ancien canal
                if email != (me.email or ""):
                    me.email_verified_at = None
                if phone != (me.phone or "") or wa != (me.whatsapp or ""):
                    me.phone_verified_at = None
            me.email, me.phone, me.whatsapp = email or me.email, phone or None, wa or None
            mob = f.get("mobile")
            if mob == "whatsapp" and f.get("wa_consent"):
                me.mobile_channel, me.wa_consent_at = "whatsapp", me.wa_consent_at or utcnow()
            else:
                me.mobile_channel = "sms"
                if mob != "whatsapp":
                    me.wa_consent_at = None if f.get("wa_withdraw") else me.wa_consent_at
            me.code_channel = f.get("code") if f.get("code") in ("email", "sms", "whatsapp") else "email"
            me.reminders = bool(f.get("reminders"))
            AuditLog.log("account.contact", target=f"user:{me.id}")
            db.session.commit()
            flash(t("saved"), "ok")
            return redirect(url_for("org.account"))
    return render_template("org/account.html", habs=sorted(me.habilitations, key=lambda h: (h.status != "active", h.id)))


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
    for h in Habilitation.query.filter(Habilitation.institute_id.in_([i.id for i in insts] or [-1]),
                                       Habilitation.status == "active", Habilitation.role.in_((RESP, TEACHER))):
        staff[h.institute_id] += 1
    edit = db.session.get(Institute, _int(request.args.get("edit"), -1))
    return render_template("org/institutes.html", insts=insts, counts=counts, staff=staff, can_edit=can_edit,
                           edit=edit if edit in insts else None, wilayas=visible_wilayas(current_user).all())


# ------------------------------------------------------------------ habilitations (CU-02)

def _can_manage_hab(me, h):
    """L'autorité qui accorde ce rôle, dans son périmètre (ou la DFEP de la wilaya), jamais sur soi-même."""
    if h.user_id == me.id:
        return False
    if h.role not in CAN_CREATE.get(me.role, set()) and not (me.role == DFEP and h.role in (COORD, RESP, TEACHER)):
        return False
    return visible_habilitations(me).filter(Habilitation.id == h.id).count() == 1


@bp.route("/comptes", methods=["GET", "POST"])
@roles_required(ADMIN, MFEP, DFEP, COORD, RESP, NESDA_DG)
def users():
    me = current_user
    creatable = [r for r in ROLES if r in CAN_CREATE.get(me.role, set())]
    lang = get_lang()
    if request.method == "POST":
        f = request.form
        action = f.get("action", "grant")
        if action == "lookup":
            from ..services import connectors as C
            st, data, src = C.identity(f.get("nin"))
            db.session.commit()
            existing = User.by_nin(f.get("nin"))
            return render_template("org/users.html", **_users_ctx(me, creatable), lookup={
                "nin": NIN.normalize(f.get("nin")), "status": st, "data": data, "source": src, "existing": existing})
        if action == "grant":
            role = f.get("role")
            raw = NIN.normalize(f.get("nin"))
            reason = (f.get("reason") or "").strip()[:200]
            if role not in creatable or not NIN.valid(raw) or not reason:
                flash(t("hab.missing"), "err")
                return redirect(url_for("org.users"))
            inst = wil = None
            if role in NEEDS_INSTITUTE:
                inst = db.session.get(Institute, _int(f.get("institute"), -1))
                if inst not in visible_institutes(me).all():
                    flash(t("form.missing"), "err")
                    return redirect(url_for("org.users"))
            elif role in NEEDS_WILAYA:
                wil = me.wilaya if me.role in (DFEP, COORD) else Wilaya.query.filter_by(code=f.get("wilaya")).first()
                if wil is None or wil not in visible_wilayas(me).all():
                    flash(t("form.missing"), "err")
                    return redirect(url_for("org.users"))
            ends = _date(f.get("ends_on"))
            u = User.by_nin(raw)
            created = u is None
            if created:
                from ..services import connectors as C
                st, data, src = C.identity(raw)
                email = (f.get("email") or "").strip().lower()[:150]
                if not email:
                    flash(t("hab.need_email"), "err")
                    return redirect(url_for("org.users"))
                u = User(name=(f.get("name") or "").strip()[:120] or "—", email=email,
                         phone=(f.get("phone") or "")[:30] or None, lang=f.get("lang") if f.get("lang") in ("ar", "fr", "en") else "ar",
                         active=True)
                u.nin = raw
                C.apply_identity(u, st, data, src)
                if (f.get("name") or "").strip():
                    u.name = f["name"].strip()[:120]
                u.set_password(gen_password() + gen_password())     # inconnu : la personne le choisit à l'activation
                db.session.add(u)
                db.session.flush()
                u.new_invite()
            if any(h.is_valid() and h.role == role and h.institute_id == (inst.id if inst else None)
                   and h.wilaya_id == ((inst.wilaya_id if inst else None) or (wil.id if wil else None)) for h in u.habilitations):
                flash(t("hab.exists"), "err")
                return redirect(url_for("org.users"))
            h = u.grant(role, institute=inst, wilaya=wil, by=me, reason=reason, ends_on=ends,
                        activated=not created)
            db.session.flush()
            AuditLog.log("habilitation.grant", target=f"user:{u.id}", details=f"{role}:{inst.code if inst else (wil.code if wil else 'national')}")
            from ..services.events import habilitation_changed
            habilitation_changed(h, "invited" if created else "granted", me)
            db.session.commit()
            flash(t("hab.invited") if created else t("hab.granted"), "ok")
            return redirect(url_for("org.users"))
        h = db.session.get(Habilitation, _int(f.get("id"), -1))
        if not h or not _can_manage_hab(me, h):
            abort(403)
        why = (f.get("why") or "").strip()[:200]
        if action in ("suspend", "revoke", "restore") and not why:
            flash(t("hab.need_reason"), "err")
            return redirect(url_for("org.users"))
        if action == "suspend" and h.status == "active":
            h.status = "suspended"
        elif action == "restore" and h.status == "suspended":
            h.status = "active"
        elif action == "revoke" and h.status in ("active", "suspended", "pending"):
            h.status = "revoked"
        elif action == "reset":
            u = h.user
            u.new_invite()
            AuditLog.log("user.reinvite", target=f"user:{u.id}")
            from ..services.events import habilitation_changed
            habilitation_changed(h, "invited", me)
            db.session.commit()
            flash(t("hab.reinvited"), "ok")
            return redirect(url_for("org.users"))
        else:
            abort(400)
        h.changed_by_id, h.changed_at, h.change_reason = me.id, utcnow(), why
        AuditLog.log(f"habilitation.{action}", target=f"user:{h.user_id}", details=f"{h.role}:{why}")
        from ..services.events import habilitation_changed
        habilitation_changed(h, {"suspend": "suspended", "revoke": "revoked", "restore": "restored"}[action], me)
        db.session.commit()
        flash(t("saved"), "ok")
        return redirect(url_for("org.users"))
    return render_template("org/users.html", **_users_ctx(me, creatable), lookup=None)


def _users_ctx(me, creatable):
    st = request.args.get("st", "active")
    q = visible_habilitations(me)
    if st in ("active", "pending", "suspended", "revoked"):
        q = q.filter(Habilitation.status == st)
    rows = q.join(User, Habilitation.user_id == User.id).order_by(Habilitation.role, User.name).all()
    counts = {k: visible_habilitations(me).filter(Habilitation.status == k).count()
              for k in ("active", "pending", "suspended", "revoked")}
    return dict(rows=rows, creatable=creatable, institutes=visible_institutes(me).all(), wilayas=visible_wilayas(me).all(),
                can_manage=lambda h: _can_manage_hab(me, h), NEEDS_INSTITUTE=NEEDS_INSTITUTE, NEEDS_WILAYA=NEEDS_WILAYA,
                st=st, counts=counts)


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
    return render_template("org/objectives.html", w=w, year=year, years=_year_choices(year),
                           insts=insts, sel_inst=sel_inst, wgrid=wgrid, igrid=igrid, sums=sums,
                           can_edit_w=can_edit_w, can_edit_i=can_edit_i, KPIS=K.KPIS, RATES=K.RATES,
                           wilayas=Wilaya.query.order_by(Wilaya.code).all(), families=K.KPI_FAMILIES)


def _next_year(label):
    y = int(label[:4]) + 1
    return f"{y}-{y + 1}"


def _year_choices(year):
    """Années proposées : les 3 dernières, l'année suivante, et toujours l'année affichée."""
    years = recent_years(3)
    years.insert(0, _next_year(years[0]))
    if year not in years:
        years.append(year)
    return sorted(set(years), reverse=True)


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
    return render_template("org/programme.html", w=w, year=year, years=_year_choices(year),
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
        q = q.filter(AuditLog.role == MFEP)
    elif me.role == NESDA_DG:
        q = q.filter(AuditLog.role.in_((NESDA_DG, NESDA)))
    elif me.role in (DFEP, COORD):
        q = q.filter(AuditLog.wilaya_id == me.wilaya_id)
    elif me.role == RESP:
        q = q.filter(AuditLog.institute_id == me.institute_id)
    page = max(1, _int(request.args.get("page"), 1))
    rows = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * 50).limit(51).all()
    return render_template("org/audit.html", rows=rows[:50], page=page, has_next=len(rows) > 50)


# ---------------------------------------------------------------- objectifs nationaux : échange Excel (MFEP)
@bp.route("/objectifs/national.xlsx")
@roles_required(ADMIN, MFEP)
def objectives_export():
    from ..services import xl
    year = request.values.get("y") or Period().year
    cur = {(o.wilaya_id, o.kpi, o.semester): o.target
           for o in Objective.query.filter_by(year=year, institute_id=None)}
    wb = xl.book()
    ws = xl.sheet(wb, t("nav.objectives"), first=True)
    ws.append([t("xl.wcode"), t("dash.table.wilaya"), t("xl.kpi_code"), t("xl.kpi"), "S1", "S2", t("xl.year")])
    xl.header(ws)
    lang = get_lang()
    for w in Wilaya.query.order_by(Wilaya.code):
        for k in K.KPIS:
            ws.append([w.code, w.name(lang), k, t("kpi." + k)] + [cur.get((w.id, k, s)) for s in (1, 2, 0)])
    xl.widths(ws, 8, 22, 14, 34, 9, 9, 9)
    ws.freeze_panes = "E2"
    return xl.send(wb, f"objectifs-{year}.xlsx")


@bp.route("/objectifs/import", methods=["POST"])
@roles_required(ADMIN, MFEP)
def objectives_import():
    from openpyxl import load_workbook
    year = request.form.get("y") or Period().year
    f = request.files.get("file")
    try:
        ws = load_workbook(f, read_only=True, data_only=True).active
        rows = list(ws.iter_rows(min_row=2, values_only=True))
    except Exception:
        flash(t("imp.unreadable"), "err")
        return redirect(url_for("org.objectives", y=year))
    wil = {w.code: w for w in Wilaya.query}
    existing = {(o.wilaya_id, o.kpi, o.semester): o for o in Objective.query.filter_by(year=year, institute_id=None)}
    n = 0
    for r in rows:
        if not r or len(r) < 7:
            continue
        w = wil.get(str(r[0] or "").strip().zfill(2))
        k = str(r[2] or "").strip()
        if not w or k not in K.KPIS:
            continue
        for sem, v in zip((1, 2, 0), r[4:7]):
            val = _float(str(v).replace(",", ".")) if v not in (None, "") else None
            o = existing.get((w.id, k, sem))
            if val is None:
                continue
            if o is None:
                o = Objective(year=year, semester=sem, wilaya_id=w.id, kpi=k)
                db.session.add(o)
            o.target, o.set_by_id = val, current_user.id
            n += 1
    AuditLog.log("objectives.import", target="national", details=f"{year}: {n} cible(s)")
    db.session.commit()
    flash(t("obj.imported", n=n), "ok")
    return redirect(url_for("org.objectives", y=year))
