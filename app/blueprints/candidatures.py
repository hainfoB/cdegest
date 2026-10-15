"""Candidatures reçues par le formulaire en 4 étapes : étude par le CDE, orientation vers une session."""
import re
from collections import Counter
from datetime import date

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


# ------------------------------------------------------------------ import Excel (fichier extrait de fp.cde.dz)
import json  # noqa: E402

from ..i18n import get_lang  # noqa: E402
from ..models import Institute, Wilaya  # noqa: E402
from ..security import visible_institutes  # noqa: E402
from ..services import importer, xl  # noqa: E402


@bp.route("/import", methods=["GET", "POST"])
@roles_required(ADMIN, DFEP, COORD, RESP)
def import_xlsx():
    insts = visible_institutes(current_user).all()
    inst = next((i for i in insts if i.id == request.values.get("i", type=int)), insts[0] if len(insts) == 1 else None)
    ctx = dict(insts=insts, inst=inst, rows=None, cols=None)
    if request.method == "POST" and request.form.get("confirm") and inst:
        rows = json.loads(request.form.get("payload") or "[]")
        n = _import(rows, inst)
        flash(t("imp.done", n=n), "ok")
        return redirect(url_for(".index"))
    if request.method == "POST":
        f = request.files.get("file")
        if not inst or not f or not f.filename.lower().endswith((".xlsx", ".xlsm")):
            flash(t("imp.need_file"), "err")
            return redirect(url_for(".import_xlsx", i=inst.id if inst else None))
        try:
            cols, rows = importer.read_rows(f)
        except Exception:  # fichier illisible
            flash(t("imp.unreadable"), "err")
            return redirect(url_for(".import_xlsx", i=inst.id))
        known = {c.phone for c in Candidature.query.filter(Candidature.institute_id == inst.id)}
        for r in rows:
            r["dup"] = r["phone"] in known
        ctx.update(rows=rows, cols=cols, fname=f.filename, has_q=any(k.startswith("q_") for k in cols),
                   ok=[r for r in rows if not r["errors"] and not r["dup"]],
                   payload=json.dumps([r for r in rows if not r["errors"] and not r["dup"]], ensure_ascii=False))
    return render_template("candidatures/import.html", **ctx)


def _d(v):
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _import(rows, inst, source="excel"):
    wil = {w.code: w for w in Wilaya.query}
    by_name = {}
    for w in wil.values():
        by_name[w.name_fr.lower()] = w
        by_name[w.name_ar] = w
    origins = {i.name_fr.lower(): i for i in Institute.query.filter_by(wilaya_id=inst.wilaya_id)}
    known = {c.phone for c in Candidature.query.filter(Candidature.institute_id == inst.id)}
    n = 0
    for r in rows:
        if r.get("errors") or not r.get("phone") or r["phone"] in known:
            continue
        wv = str(r.get("wilaya") or "").strip()
        code = re.match(r"\d{1,2}", wv)
        w = (wil.get(code.group(0).zfill(2)) if code else None) or by_name.get(wv.lower()) or inst.wilaya
        o = origins.get((r.get("origin") or "").lower())
        c = Candidature(answers=r.get("answers") or "", last_name=str(r["last_name"])[:80], first_name=str(r["first_name"])[:80],
                        phone=r["phone"], email=r.get("email"), sex=r.get("sex"),
                        birth_date=_d(r.get("birth_date")),
                        wilaya_id=w.id, pstatus=r.get("pstatus") or "diplome", specialty=r.get("specialty") or "",
                        diploma_year=r.get("diploma_year"), idea=r.get("idea"),
                        origin_institute_id=o.id if o else None, institute_id=inst.id, source=source,
                        consent_at=utcnow())
        db.session.add(c)
        known.add(r["phone"])
        n += 1
    AuditLog.log("candidature.import", target=f"institute:{inst.id}", details=f"{n} ligne(s)")
    db.session.commit()
    return n


@bp.route("/modele.xlsx")
@roles_required(ADMIN, DFEP, COORD, RESP)
def template():
    wb = xl.book()
    ws = xl.sheet(wb, t("nav.candidatures"), first=True)
    ws.append(importer.template_headers(get_lang()))
    xl.header(ws)
    ws.append(["Saidi", "Lina", "0550123456", "", "12/03/2002", "F", "34", "Informatique", 2025, "", "Agence web",
               "لا", "نعم", "نعم", "لا", "نعم", "نعم"])
    xl.widths(ws, *([16] * 11 + [30] * 6))
    return xl.send(wb, "modele-candidatures-fp.cde.dz.xlsx")
