"""Échanges avec les administrations (EP-12) et boîte d'envoi des messages simulés (EP-11)."""
import hmac
import time
from datetime import date, timedelta

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from .. import nin as NIN
from ..extensions import csrf, db
from ..i18n import get_lang, t
from ..models import ApiCall, AuditLog, Candidature, Enrollment, Notification, Participant, Session, User
from ..security import ADMIN, COORD, DFEP, MFEP, RESP, roles_required, visible_institute_ids
from ..services import connectors as C
from ..services import notify as N
from ..services.messages import CATALOG, CATEGORY_LABEL

bp = Blueprint("integration", __name__)


# ------------------------------------------------------------------ connecteurs (US-1201)

@bp.route("/connecteurs", methods=["GET", "POST"])
@roles_required(ADMIN, MFEP)
def connectors():
    test = None
    if request.method == "POST":
        act = request.form.get("action")
        if act == "mode":
            code, mode = request.form.get("code"), request.form.get("mode")
            if code not in C.CONNECTORS or mode not in C.MODES:
                abort(400)
            old = C.mode(code)
            C.set_mode(code, mode, current_user)
            AuditLog.log("connector.mode", target=code, details=f"{old} → {mode}")
            db.session.commit()
            flash(t("conn.mode_saved"), "ok")
            return redirect(url_for(".connectors"))
        if act == "test":
            raw = request.form.get("nin")
            test = {"nin": NIN.mask(raw), "etat_civil": C.identity(raw), "mfep_diplomes": C.diplomas(raw), "men": C.level(raw)}
            db.session.commit()
        if act in ("out_nesda", "out_stats"):
            test = {"out": act, "json": _nesda_payload(date.today() - timedelta(days=120), None, 1)
                    if act == "out_nesda" else _stats_payload(None)}
            C.log_out("nesda" if act == "out_nesda" else "mfep_stats", "servi", fields="console")
            db.session.commit()
    stats = {}
    since = date.today() - timedelta(days=30)
    for code in C.CONNECTORS:
        q = ApiCall.query.filter(ApiCall.connector == code, ApiCall.created_at >= since)
        stats[code] = {"n": q.count(), "ok": q.filter(ApiCall.result.in_(("trouve", "servi"))).count(),
                       "ko": q.filter(ApiCall.result.in_(("indisponible", "refuse"))).count()}
    calls = ApiCall.query.order_by(ApiCall.id.desc()).limit(40).all()
    modes = {code: C.mode(code) for code in C.CONNECTORS}
    unverified = Candidature.query.filter(Candidature.status.in_(("nouvelle", "retenue")),
                                          Candidature.identity_source != "etat_civil").count()
    return render_template("integration/connectors.html", conns=C.CONNECTORS, modes=modes, MODES=C.MODES, stats=stats,
                           calls=calls, test=test, unverified=unverified,
                           keys={"nesda": bool(current_app.config.get("NESDA_API_KEY")),
                                 "mfep": bool(current_app.config.get("MFEP_API_KEY"))})


# ------------------------------------------------------------------ boîte d'envoi simulée

@bp.route("/messages", methods=["GET", "POST"])
@roles_required(ADMIN, MFEP, DFEP, COORD, RESP)
def outbox():
    me = current_user
    if request.method == "POST":
        if me.role not in (ADMIN, MFEP):
            abort(403)
        act = request.form.get("action")
        from ..services import events as E
        if act == "run":
            n = N.deliver_due()
            n += E.run_reminders()
            db.session.commit()
            flash(t("out.ran", n=n), "ok")
        elif act == "digest":
            n = E.run_digests()
            db.session.commit()
            flash(t("out.digests", n=n), "ok")
        return redirect(url_for(".outbox"))
    N.deliver_due()
    db.session.commit()
    q = Notification.query
    if me.role in (DFEP, COORD, RESP):
        # messages concernant les personnes de mon périmètre (demandeurs et stagiaires de mes CDE, agents)
        ids = visible_institute_ids(me) or [-1]
        uids = {u for (u,) in db.session.query(Candidature.user_id).filter(Candidature.institute_id.in_(ids), Candidature.user_id.isnot(None))}
        uids |= {u for (u,) in db.session.query(Participant.user_id).join(Enrollment, Enrollment.participant_id == Participant.id)
                 .join(Session, Session.id == Enrollment.session_id).filter(Session.institute_id.in_(ids), Participant.user_id.isnot(None))}
        q = q.filter(Notification.user_id.in_(uids or {-1}), Notification.code != "M-01")
    f = {k: request.args.get(k) for k in ("code", "channel", "status", "cat")}
    if f["code"] in CATALOG:
        q = q.filter(Notification.code == f["code"])
    if f["channel"] in ("email", "sms", "whatsapp"):
        q = q.filter(Notification.channel == f["channel"])
    if f["status"] in ("delivered", "scheduled", "failed"):
        q = q.filter(Notification.status == f["status"])
    if f["cat"] in ("A", "B", "C", "D"):
        q = q.filter(Notification.category == f["cat"])
    rows = q.order_by(Notification.id.desc()).limit(150).all()
    base = Notification.query if me.role in (ADMIN, MFEP) else q
    counts = {s: base.filter(Notification.status == s).count() for s in ("delivered", "scheduled", "failed")}
    by_ch = {c: base.filter(Notification.channel == c).count() for c in ("email", "sms", "whatsapp")}
    return render_template("integration/outbox.html", rows=rows, f=f, CATALOG=CATALOG, CAT=CATEGORY_LABEL,
                           counts=counts, by_ch=by_ch, can_run=me.role in (ADMIN, MFEP), show_codes=me.role in (ADMIN, MFEP))


@bp.route("/messages/modeles")
@roles_required(ADMIN, MFEP, DFEP, COORD, RESP)
def templates():
    return render_template("integration/templates.html", CATALOG=CATALOG, CAT=CATEGORY_LABEL)


# ------------------------------------------------------------------ API de sortie (CDC technique §6.6)

def _check_key(cfg_key, connector):
    key = current_app.config.get(cfg_key)
    if not key:
        abort(404)                                  # API fermée tant qu'aucune clé n'est configurée
    if not hmac.compare_digest(request.headers.get("X-Api-Key", ""), key):
        C.log_out(connector, "refuse")
        db.session.commit()
        abort(401)
    if C.mode(connector) == "desactive":
        abort(503)


def _nesda_payload(since, wcode, page, per=200):
    q = (Enrollment.query.join(Session, Session.id == Enrollment.session_id)
         .filter(Session.nesda_status == "validated", Enrollment.cert_no.isnot(None), Enrollment.cert_issued_on >= since))
    if wcode:
        from ..models import Institute, Wilaya
        q = q.join(Institute, Institute.id == Session.institute_id).join(Wilaya, Wilaya.id == Institute.wilaya_id).filter(Wilaya.code == wcode)
    total = q.count()
    rows = q.order_by(Enrollment.id).offset((page - 1) * per).limit(per).all()
    from ..services.training import enrollment_stats
    out = []
    for e in rows:
        p, s = e.participant, e.session
        out.append({"nin": p.nin, "nom": p.last_name, "prenom": p.first_name,
                    "date_naissance": p.birth_date.isoformat() if p.birth_date else None, "telephone": p.phone,
                    "formation": s.template.code if s.template else None, "session": s.slug,
                    "debut": s.starts_on.isoformat() if s.starts_on else None, "fin": s.ends_on.isoformat() if s.ends_on else None,
                    "assiduite": enrollment_stats(e)["rate"], "numero_attestation": e.cert_no, "suite": p.nesda_status})
    return {"page": page, "pages": max(1, -(-total // per)), "total": total, "formes": out}


@bp.route("/api/v1/nesda/formes")
@csrf.exempt
def api_nesda_formes():
    _check_key("NESDA_API_KEY", "nesda")
    try:
        since = date.fromisoformat(request.args.get("depuis") or "2000-01-01")
    except ValueError:
        abort(400)
    data = _nesda_payload(since, request.args.get("wilaya"), max(1, request.args.get("page", 1, type=int)))
    C.log_out("nesda", "servi", fields=f"formes:{len(data['formes'])}")
    db.session.commit()
    return jsonify(data)


@bp.route("/api/v1/nesda/suites", methods=["POST"])
@csrf.exempt
def api_nesda_suites():
    """Entrée : la NESDA renvoie la suite donnée aux projets (déposé, accepté, abouti)."""
    _check_key("NESDA_API_KEY", "nesda")
    rows = request.get_json(silent=True) or []
    if not isinstance(rows, list):
        abort(400)
    mapping = {"depose": "depose", "accepte": "accepte", "abouti": "abouti"}
    done = 0
    for r in rows:
        if not isinstance(r, dict) or r.get("etat") not in mapping:
            continue
        e = Enrollment.query.filter_by(cert_no=str(r.get("numero_attestation", ""))).first()
        if e is None or e.participant.nin_hash != NIN.fingerprint(r.get("nin")):
            continue
        p = e.participant
        p.nesda_status = mapping[r["etat"]]
        try:
            p.nesda_status_on = date.fromisoformat(r.get("date") or date.today().isoformat())
        except ValueError:
            p.nesda_status_on = date.today()
        db.session.add(ApiCall(connector="nesda", direction="in", mode=C.mode("nesda"), nin_hash=p.nin_hash,
                               fields="suite", result="trouve", duration_ms=0))
        done += 1
    db.session.commit()
    return jsonify({"recus": len(rows), "appliques": done})


def _stats_payload(year):
    from ..models import Wilaya
    from ..services import kpi as K
    from ..services.period import Period
    period = Period(year, "A") if year else Period(None, "A")
    out = []
    for w in Wilaya.query.order_by(Wilaya.code):
        ids = [i.id for i in w.institutes]
        if not ids:
            continue
        vals = K.kpis_for_institutes(ids, period)
        out.append({"wilaya": w.code, "indicateurs": {k: vals.get(k) for k in K.KPIS}})
    return {"annee": period.year, "wilayas": out}


@bp.route("/api/v1/mfep/statistiques")
@csrf.exempt
def api_mfep_stats():
    _check_key("MFEP_API_KEY", "mfep_stats")
    data = _stats_payload(request.args.get("annee"))
    C.log_out("mfep_stats", "servi", fields="indicateurs")
    db.session.commit()
    return jsonify(data)


@bp.route("/api/v1/notifications/statut", methods=["POST"])
@csrf.exempt
def api_notif_status():
    """Accusés de remise des passerelles (réel) : désactivé dans le prototype, tout est simulé."""
    abort(404)
