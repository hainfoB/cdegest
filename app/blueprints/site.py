"""Site public d'information (inscription, formation, FAQ, événements, signalements) et sa gestion."""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .. import site_content as C
from ..extensions import db
from ..i18n import get_lang, t
from ..models import AuditLog, Event, Institute, Ticket, Wilaya
from ..security import ADMIN, COORD, DFEP, MFEP, NATIONAL, NESDA, NESDA_DG, RESP, WILAYA_LEVEL, roles_required
from ..utils import utcnow
from .public import _limited

bp = Blueprint("site", __name__)

EVENT_MANAGERS = (ADMIN, MFEP, DFEP, COORD, RESP)
TICKET_HANDLERS = (ADMIN, DFEP, COORD, RESP, NESDA, NESDA_DG)
NESDA_CATS = ("presence", "attestation")
STATUSES = ("open", "progress", "resolved", "closed")


# ---------------------------------------------------------------- public pages

def _upcoming(limit=None, wilaya_id=None):
    q = Event.query.filter(Event.published.is_(True),
                           db.or_(Event.ends_on >= date.today(), db.and_(Event.ends_on.is_(None), Event.starts_on >= date.today())))
    if wilaya_id:
        q = q.filter(db.or_(Event.wilaya_id == wilaya_id, Event.wilaya_id.is_(None)))
    q = q.order_by(Event.starts_on)
    return q.limit(limit).all() if limit else q.all()


@bp.route("/le-cde")
def about():
    return render_template("site/about.html", page="about")


@bp.route("/comment-s-inscrire")
def howto():
    return render_template("site/howto.html", page="howto", c=C.pick(C.INSCRIPTION, get_lang()))


@bp.route("/la-formation")
def training():
    return render_template("site/training.html", page="training", c=C.pick(C.FORMATION, get_lang()))


@bp.route("/faq")
def faq():
    return render_template("site/faq.html", page="faq", groups=C.pick(C.FAQ, get_lang()))


@bp.route("/evenements")
def events():
    wcode = request.args.get("w")
    w = Wilaya.query.filter_by(code=wcode).first() if wcode else None
    past = request.args.get("passes") == "1"
    if past:
        rows = (Event.query.filter(Event.published.is_(True), Event.starts_on < date.today())
                .filter(db.or_(Event.wilaya_id == w.id, Event.wilaya_id.is_(None)) if w else db.true())
                .order_by(Event.starts_on.desc()).limit(60).all())
    else:
        rows = _upcoming(wilaya_id=w.id if w else None)
    wil_ids = {e.wilaya_id for e in Event.query.filter(Event.published.is_(True)) if e.wilaya_id}
    return render_template("site/events.html", page="events", rows=rows, past=past, wcode=wcode,
                           wilayas=Wilaya.query.filter(Wilaya.id.in_(wil_ids or [-1])).order_by(Wilaya.code).all())


@bp.route("/evenements/<int:eid>")
def event(eid):
    e = db.session.get(Event, eid)
    if not e or not e.published:
        abort(404)
    return render_template("site/event.html", page="events", e=e)


@bp.route("/signaler", methods=["GET", "POST"])
def report():
    wilayas = Wilaya.query.order_by(Wilaya.code).all()
    insts = Institute.query.filter(Institute.active.is_(True)).order_by(Institute.code).all()
    f = request.form
    error = None
    if request.method == "POST":
        if f.get("website"):                      # honeypot
            abort(400)
        if _limited("ticket", 10):
            error = t("login.blocked")
        elif f.get("category") not in C.TICKET_CATS or not (f.get("name", "").strip() and f.get("subject", "").strip()
                                                              and f.get("message", "").strip()):
            error = t("tk.err_required")
        elif not (f.get("phone", "").strip() or f.get("email", "").strip()):
            error = t("tk.err_contact")
        elif not f.get("consent"):
            error = t("tk.err_consent")
        else:
            inst = db.session.get(Institute, f.get("institute", type=int)) if f.get("institute") else None
            w = inst.wilaya if inst else Wilaya.query.filter_by(code=f.get("wilaya")).first()
            msg = f["message"].strip()
            if f.get("cand_ref", "").strip():
                msg = f"[{t('tk.cand_ref')} : {f['cand_ref'].strip()[:20]}]\n" + msg
            tk = Ticket(category=f["category"], name=f["name"].strip()[:120], phone=f.get("phone", "").strip()[:20] or None,
                        email=f.get("email", "").strip()[:150] or None, wilaya=w, institute=inst,
                        subject=f["subject"].strip()[:160], message=msg[:4000])
            db.session.add(tk)
            db.session.commit()
            return redirect(url_for("site.ticket_status", token=tk.token, new=1))
    return render_template("site/report.html", page="report", wilayas=wilayas, insts=insts, f=f, error=error,
                           cats=C.TICKET_CATS)


@bp.route("/signalement", methods=["POST"])
def ticket_lookup():
    ref = request.form.get("ref", "").strip().upper()
    contact = request.form.get("contact", "").strip().lower()
    if _limited("ticket_lookup", 30):
        flash(t("login.blocked"), "err")
        return redirect(url_for("site.report") + "#suivi")
    tk = Ticket.query.filter_by(ref=ref).first() if ref else None
    if tk and contact and contact in ((tk.phone or "").lower(), (tk.email or "").lower()):
        return redirect(url_for("site.ticket_status", token=tk.token))
    flash(t("tk.not_found"), "err")
    return redirect(url_for("site.report") + "#suivi")


@bp.route("/signalement/<token>")
def ticket_status(token):
    tk = Ticket.query.filter_by(token=token).first_or_404()
    return render_template("site/ticket.html", page="report", tk=tk, new=request.args.get("new"))


# ---------------------------------------------------------------- back office: events

def _events_scope(user):
    q = Event.query
    if user.role in NATIONAL:
        return q
    if user.role in WILAYA_LEVEL:
        return q.filter(Event.wilaya_id == (user.wilaya_id or -1))
    return q.filter(Event.institute_id == (user.institute_id or -1))


def _date(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


@bp.route("/gestion/evenements", methods=["GET", "POST"])
@roles_required(*EVENT_MANAGERS)
def manage_events():
    u = current_user
    scope = _events_scope(u)
    edit = scope.filter(Event.id == request.args.get("edit", type=int)).first() if request.args.get("edit") else None
    from ..security import visible_institutes, visible_wilayas
    insts = visible_institutes(u).all()
    wilayas = visible_wilayas(u).all()
    if request.method == "POST":
        f = request.form
        e = scope.filter(Event.id == f.get("id", type=int)).first() if f.get("id") else Event(created_by=u)
        if e is None:
            abort(404)
        starts = _date(f.get("starts_on"))
        if not (f.get("title_fr", "").strip() and f.get("title_ar", "").strip() and starts):
            flash(t("ev.err_required"), "err")
            return redirect(url_for("site.manage_events", edit=e.id) if e.id else url_for("site.manage_events"))
        e.kind = f.get("kind") if f.get("kind") in C.EVENT_KINDS else "evenement"
        e.title_fr, e.title_ar = f["title_fr"].strip()[:160], f["title_ar"].strip()[:160]
        e.body_fr, e.body_ar = f.get("body_fr", "").strip(), f.get("body_ar", "").strip()
        e.starts_on, e.ends_on = starts, _date(f.get("ends_on"))
        if e.ends_on and e.ends_on < e.starts_on:
            e.ends_on = None
        e.place = f.get("place", "").strip()[:160] or None
        # perimeter: an event never leaves the author's scope
        inst_id = f.get("institute", type=int)
        inst = next((i for i in insts if i.id == inst_id), None)
        if u.role == RESP:
            inst = u.institute
        if inst:
            e.institute, e.wilaya = inst, inst.wilaya
        elif u.role in WILAYA_LEVEL:
            e.institute, e.wilaya = None, u.wilaya
        else:  # national roles
            w = next((w for w in wilayas if w.code == f.get("wilaya")), None)
            e.institute, e.wilaya = None, w
        e.published = bool(f.get("published"))
        db.session.add(e)
        db.session.flush()
        AuditLog.log("event.save", f"event:{e.id}", e.title_fr)
        db.session.commit()
        flash(t("saved"), "ok")
        return redirect(url_for("site.manage_events"))
    rows = scope.order_by(Event.starts_on.desc()).all()
    return render_template("site/manage_events.html", rows=rows, edit=edit, insts=insts, wilayas=wilayas,
                           kinds=C.EVENT_KINDS)


@bp.route("/gestion/evenements/<int:eid>/<action>", methods=["POST"])
@roles_required(*EVENT_MANAGERS)
def event_action(eid, action):
    e = _events_scope(current_user).filter(Event.id == eid).first_or_404()
    if action == "publier":
        e.published = not e.published
        AuditLog.log("event.publish" if e.published else "event.unpublish", f"event:{e.id}", e.title_fr)
    elif action == "supprimer":
        AuditLog.log("event.delete", f"event:{e.id}", e.title_fr)
        db.session.delete(e)
    else:
        abort(404)
    db.session.commit()
    flash(t("saved"), "ok")
    return redirect(url_for("site.manage_events"))


# ---------------------------------------------------------------- back office: tickets

def tickets_scope(user):
    q = Ticket.query
    if user.role == ADMIN:
        return q
    if user.role == NESDA_DG:
        return q.filter(Ticket.category.in_(NESDA_CATS))
    if user.role == NESDA:
        return q.filter(Ticket.category.in_(NESDA_CATS), Ticket.wilaya_id == (user.wilaya_id or -1))
    if user.role in (DFEP, COORD):
        return q.filter(Ticket.wilaya_id == (user.wilaya_id or -1))
    if user.role == RESP:
        return q.filter(Ticket.institute_id == (user.institute_id or -1))
    return q.filter(Ticket.id == -1)


@bp.route("/gestion/signalements")
@roles_required(*TICKET_HANDLERS)
def manage_tickets():
    st = request.args.get("st", "active")
    q = tickets_scope(current_user)
    if st == "active":
        q = q.filter(Ticket.status.in_(("open", "progress")))
    elif st in STATUSES:
        q = q.filter(Ticket.status == st)
    rows = q.order_by(Ticket.created_at.desc()).limit(300).all()
    counts = {s: tickets_scope(current_user).filter(Ticket.status == s).count() for s in STATUSES}
    return render_template("site/manage_tickets.html", rows=rows, st=st, counts=counts, statuses=STATUSES)


@bp.route("/gestion/signalements/<int:tid>", methods=["GET", "POST"])
@roles_required(*TICKET_HANDLERS)
def manage_ticket(tid):
    tk = tickets_scope(current_user).filter(Ticket.id == tid).first_or_404()
    if request.method == "POST":
        st = request.form.get("status")
        if st in STATUSES:
            tk.status = st
        reply = request.form.get("reply", "").strip()
        if reply:
            tk.reply = reply[:4000]
        tk.handled_by, tk.handled_at = current_user, utcnow()
        AuditLog.log("ticket.update", f"ticket:{tk.ref}", tk.status)
        db.session.commit()
        flash(t("saved"), "ok")
        return redirect(url_for("site.manage_ticket", tid=tk.id))
    return render_template("site/manage_ticket.html", tk=tk, statuses=STATUSES)
