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
    """Inscription depuis le catalogue : NIN, vérification d'identité, compte, demande orientée vers la session (RG-38)."""
    s = Session.query.filter_by(slug=slug).first_or_404()
    error = None
    logged = current_user.is_authenticated and current_user.nin_hash is not None
    if request.method == "POST":
        f = request.form
        raw = NIN.normalize(f.get("nin")) if not logged else current_user.nin
        birth = _date(f.get("birth_date")) if not logged else current_user.birth_date
        if s.status != "open":
            error = t("pub.closed")
        elif _limited("register", 20):
            error = t("login.blocked")
        elif not f.get("consent") or not f.get("phone") or (not logged and not (raw and birth and f.get("email"))):
            error = t("form.missing")
        else:
            err, ident, src = (None, None, None) if logged else check_identity(raw, birth)
            existing = None if logged else User.by_nin(raw)
            pwd = f.get("password") or ""
            if err:
                error = err
            elif existing is not None:
                error = t("nin.has_account")
            elif not logged and not ident and not (f.get("last_name") and f.get("first_name")):
                error = t("nin.need_names")
            elif not logged and (len(pwd) < 10 or pwd != f.get("password2")):
                error = t("acc.bad_new")
            else:
                phone = _digits(f["phone"])
                contact = {"last_name": (ident or {}).get("nom_lat") or f.get("last_name", "").strip()[:80],
                           "first_name": (ident or {}).get("prenom_lat") or f.get("first_name", "").strip()[:80],
                           "email": (f.get("email") or "").strip().lower()[:150] or None, "phone": phone,
                           "mobile": f.get("mobile"), "wa_consent": bool(f.get("wa_consent")), "birth_date": birth,
                           "sex": f.get("sex") if f.get("sex") in ("F", "M") else None}
                if logged:
                    u, created = current_user._get_current_object(), False
                else:
                    u, created = ensure_account(raw, ident, src, contact, pwd)
                p = Participant.query.filter_by(nin_hash=u.nin_hash).first() or Participant(phone=phone)
                p.nin = u.nin
                p.user_id = u.id
                p.last_name, p.first_name = (u.name.split(" ", 1)[-1] if logged else contact["last_name"]), (u.name.split(" ", 1)[0] if logged else contact["first_name"])
                p.phone, p.email = phone, contact["email"] or u.email
                p.sex, p.birth_date = u.sex, u.birth_date
                p.identity_source = u.identity_source
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
                    c = Candidature(last_name=p.last_name, first_name=p.first_name, phone=phone, email=p.email,
                                    sex=p.sex, birth_date=p.birth_date, wilaya_id=p.wilaya_id, institute_id=s.institute_id,
                                    pstatus=p.status, specialty=p.specialty or "", consent_at=utcnow(), source="catalogue",
                                    status="orientee", user_id=u.id, identity_source=u.identity_source, answers="")
                    c.nin = u.nin
                    db.session.add(c)
                    db.session.flush()
                    from ..services import events as E
                    E.candidature_received(c)
                    T.place_enrollment(e)
                    c.enrollment = e
                    E.candidature_oriented(c, s)
                    AuditLog.log("enrollment.public", target=f"session:{s.id}")
                if created:
                    start_code(u, url_for("public.ticket", token=e.token))
                    db.session.commit()
                    return redirect(url_for("auth.code"))
                db.session.commit()
                return redirect(url_for("public.ticket", token=e.token))
    return render_template("public/register.html", s=s, error=error, logged=logged,
                           wilayas=Wilaya.query.order_by(Wilaya.code).all())


def _date(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


# ------------------------------------------------------------------ compte du candidat (NIN pour tous, RG-01)
from flask import session as _sess  # noqa: E402
from flask_login import current_user  # noqa: E402

from .. import nin as NIN  # noqa: E402
from ..models import User  # noqa: E402
from ..services import connectors as CN  # noqa: E402


def _digits(v, n=20):
    return "".join(ch for ch in str(v or "") if ch.isdigit() or ch == "+")[:n]


def check_identity(raw_nin, birth):
    """Interroge l'état civil (ou son simulateur). Renvoie (erreur, données, source)."""
    if not NIN.valid(raw_nin):
        return t("nin.invalid"), None, None
    st, data, src = CN.identity(raw_nin)
    db.session.commit()
    if st == "trouve" and birth and data["date_naissance"] != birth.isoformat():
        return t("nin.birth_mismatch"), None, None
    if st == "inconnu":
        return t("nin.unknown"), None, None
    return None, data, src


def ensure_account(raw_nin, ident, src, contact, password):
    """Crée le compte « candidat » d'une personne (ou renvoie le compte existant). Renvoie (user, créé)."""
    u = User.by_nin(raw_nin)
    if u is not None:
        return u, False
    u = User(name=f"{contact['first_name']} {contact['last_name']}".strip() or "—", email=contact.get("email"),
             phone=contact.get("phone"), lang=contact.get("lang") or "ar",
             mobile_channel="whatsapp" if contact.get("mobile") == "whatsapp" and contact.get("wa_consent") else "sms",
             code_channel="email")
    u.nin = raw_nin
    if contact.get("wa_consent") and contact.get("mobile") == "whatsapp":
        u.wa_consent_at = utcnow()
    if ident:
        CN.apply_identity(u, "trouve", ident, src)
    else:
        u.birth_date, u.sex, u.identity_source = contact.get("birth_date"), contact.get("sex"), "declaratif"
    u.set_password(password)
    db.session.add(u)
    db.session.flush()
    u.grant("candidat", reason="inscription en ligne")
    AuditLog.log("account.create", target=f"user:{u.id}", details="candidat", user=u)
    return u, True


def start_code(u, nxt):
    """Après la création du compte : code de confirmation du canal, puis ouverture de l'espace."""
    from ..services import otp as OTP
    _sess["pre"] = {"uid": u.id, "purpose": "login", "remember": False, "next": nxt}
    OTP.issue(u, "login", "email")


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


# ------------------------------------------------------------- inscription en 4 étapes (modèle fp.cde.dz)
from flask import session as fsession  # noqa: E402

from ..models import Candidature, READINESS_Q  # noqa: E402

SECTORS = ("agri", "artisanat", "btp", "commerce", "industrie", "numerique", "services", "tourisme", "autre")


@bp.route("/inscription", methods=["GET", "POST"])
@bp.route("/inscription/<int:step>", methods=["GET", "POST"])
def apply(step=1):
    """CU-03 : questionnaire, identité par NIN (état civil), parcours (MFEP, Éducation nationale), CDE, compte."""
    data = fsession.get("cand", {})
    step = max(1, min(4, step))
    if step > 1 and not data.get("s1"):
        return redirect(url_for("public.apply", step=1))
    if step > 2 and not data.get("s2"):
        return redirect(url_for("public.apply", step=2))
    logged = current_user.is_authenticated and current_user.nin_hash is not None
    error = None
    if request.method == "POST":
        f = request.form
        if step == 1:
            if any(f.get(k) not in ("0", "1") for k in READINESS_Q):
                error = t("form.missing")
            else:
                data["s1"] = {k: f[k] for k in READINESS_Q}
        elif step == 2:
            raw = current_user.nin if logged else NIN.normalize(f.get("nin"))
            birth = current_user.birth_date if logged else _date(f.get("birth_date"))
            if not (raw and birth and f.get("phone") and f.get("email") and f.get("wilaya")):
                error = t("form.missing")
            else:
                err, ident, src = (None, None, current_user.identity_source) if logged else check_identity(raw, birth)
                pending = Candidature.query.filter(Candidature.nin_hash == NIN.fingerprint(raw),
                                                   Candidature.status.in_(("nouvelle", "retenue"))).first()
                if err:
                    error = err
                elif pending is not None:                       # RG-07 : une demande en cours par NIN
                    error = t("nin.pending", ref=pending.short_ref)
                elif not logged and User.by_nin(raw) is not None:
                    error = t("nin.has_account")
                elif not logged and not ident and not (f.get("last_name") and f.get("first_name")):
                    error = t("nin.need_names")
                else:
                    if logged:
                        ln, fn = current_user.name.split(" ", 1)[-1], current_user.name.split(" ", 1)[0]
                        sex = current_user.sex
                    else:
                        ln = (ident or {}).get("nom_lat") or f.get("last_name", "").strip()[:80]
                        fn = (ident or {}).get("prenom_lat") or f.get("first_name", "").strip()[:80]
                        sex = (ident or {}).get("sexe") or (f.get("sex") if f.get("sex") in ("F", "M") else "")
                    _st, dip, dsrc = CN.diplomas(raw)
                    _st2, lev, lsrc = CN.level(raw)
                    db.session.commit()
                    data["s2"] = {"nin_enc": NIN.encrypt(raw), "nin_masked": NIN.mask(raw), "birth_date": birth.isoformat(),
                                  "last_name": ln, "first_name": fn, "sex": sex or "", "src": src or "declaratif",
                                  "name_ar": f"{(ident or {}).get('prenom_ar', '')} {(ident or {}).get('nom_ar', '')}".strip(),
                                  "phone": _digits(f.get("phone")), "email": (f.get("email") or "").strip().lower()[:150],
                                  "mobile": "whatsapp" if f.get("mobile") == "whatsapp" else "sms",
                                  "wa_consent": bool(f.get("wa_consent")), "wilaya": f.get("wilaya"),
                                  "diploma": f"{dip[0]['diplome']} — {dip[0]['specialite']}" if dip else "",
                                  "diploma_year": dip[0]["annee"] if dip else "", "dsrc": dsrc,
                                  "level": lev["libelle"] if lev else "", "lsrc": lsrc}
        elif step == 3:
            if not f.get("specialty"):
                error = t("form.missing")
            else:
                data["s3"] = {k: (f.get(k) or "").strip()[:1000] for k in
                              ("pstatus", "origin", "specialty", "diploma_year", "idea", "sector")}
        else:
            inst = db.session.get(Institute, f.get("institute", type=int) or 0)
            pwd = f.get("password") or ""
            if not inst or not f.get("consent"):
                error = t("form.missing")
            elif not logged and (len(pwd) < 10 or pwd != f.get("password2")):
                error = t("acc.bad_new")
            elif _limited("apply", 10):
                error = t("login.blocked")
            else:
                c, u, created = _save_candidature(data, inst, pwd)
                fsession.pop("cand", None)
                if created:
                    start_code(u, url_for("espace.home"))
                    db.session.commit()
                    return redirect(url_for("auth.code"))
                db.session.commit()
                return redirect(url_for("espace.home") if logged else url_for("public.candidature", ref=c.ref))
        fsession["cand"] = data
        if not error and step < 4:
            return redirect(url_for("public.apply", step=step + 1))
    ctx = {"logged": logged}
    wcode = (data.get("s2") or {}).get("wilaya")
    w = Wilaya.query.filter_by(code=wcode).first() if wcode else None
    if step == 2:
        ctx["wilayas"] = Wilaya.query.order_by(Wilaya.code).all()
    if step == 3:
        ctx["origins"] = Institute.query.filter_by(wilaya_id=w.id).order_by(Institute.code).all() if w else []
        ctx["sectors"] = SECTORS
    if step == 4:
        ctx["cdes"] = (Institute.query.filter_by(wilaya_id=w.id, active=True).order_by(Institute.code).all()
                       if w else [])
        ctx["wil"] = w
        ctx["profile"] = Candidature(answers=_answers(data)).profile
    return render_template("public/apply.html", step=step, data=data, error=error, q=READINESS_Q, **ctx)


def _answers(data):
    return ",".join(f"{k}={v}" for k, v in (data.get("s1") or {}).items())


def _save_candidature(data, inst, password):
    s2, s3 = data.get("s2", {}), data.get("s3", {})
    raw = NIN.decrypt(s2.get("nin_enc"))
    w = Wilaya.query.filter_by(code=s2.get("wilaya")).first()
    try:
        year = int(s3.get("diploma_year") or 0) or None
    except ValueError:
        year = None
    origin = db.session.get(Institute, int(s3["origin"])) if (s3.get("origin") or "").isdigit() else None
    contact = {"last_name": s2.get("last_name", ""), "first_name": s2.get("first_name", ""), "email": s2.get("email") or None,
               "phone": s2.get("phone"), "mobile": s2.get("mobile"), "wa_consent": s2.get("wa_consent"),
               "birth_date": _date(s2.get("birth_date")), "sex": s2.get("sex") or None}
    if current_user.is_authenticated and current_user.nin_hash == NIN.fingerprint(raw):
        u, created = current_user._get_current_object(), False
        u.grant("candidat", reason="nouvelle demande")
    else:
        ident = None
        if s2.get("src") in ("etat_civil", "simule"):
            ident = {"nom_lat": s2["last_name"], "prenom_lat": s2["first_name"], "sexe": s2.get("sex") or None,
                     "date_naissance": s2["birth_date"]}
        u, created = ensure_account(raw, ident, s2.get("src"), contact, password)
    c = Candidature(answers=_answers(data), last_name=s2.get("last_name", "")[:80],
                    first_name=s2.get("first_name", "")[:80], sex=s2.get("sex") if s2.get("sex") in ("F", "M") else None,
                    birth_date=_date(s2.get("birth_date")), phone=s2.get("phone"), email=s2.get("email") or None,
                    wilaya_id=w.id if w else inst.wilaya_id,
                    pstatus="stagiaire" if s3.get("pstatus") == "stagiaire" else "diplome",
                    origin_institute_id=origin.id if origin else None, specialty=s3.get("specialty", "")[:120],
                    diploma_year=year, idea=s3.get("idea") or None,
                    sector=s3.get("sector") if s3.get("sector") in SECTORS else None,
                    institute_id=inst.id, consent_at=utcnow(), user_id=u.id,
                    identity_source=s2.get("src") or "declaratif", identity_checked_at=utcnow() if s2.get("src") != "declaratif" else None,
                    diploma=s2.get("diploma") or None, diploma_source=s2.get("dsrc"), level=s2.get("level") or None,
                    level_source=s2.get("lsrc"))
    c.nin = raw
    db.session.add(c)
    db.session.flush()
    AuditLog.log("candidature.new", target=f"candidature:{c.id}", user=u)
    from ..services import events as E
    E.candidature_received(c)
    return c, u, created


@bp.route("/candidature/<ref>")
def candidature(ref):
    c = Candidature.query.filter_by(ref=ref).first_or_404()
    return render_template("public/candidature.html", c=c)


@bp.route("/api/fp/candidatures", methods=["POST"])
@csrf.exempt
def api_fp_candidatures():
    """Transfert depuis fp.cde.dz (bouton « Transférer ») : liste JSON d'inscrits, clé dans l'en-tête X-Api-Key.
    Mêmes champs que l'import Excel, plus « cde » (code de l'institut, ex. INSFP-BBA-01)."""
    import hmac
    from flask import current_app
    key = current_app.config.get("FP_API_KEY")
    if not key:
        abort(404)
    if not hmac.compare_digest(request.headers.get("X-Api-Key", ""), key):
        abort(401)
    from ..blueprints.candidatures import _import
    rows = request.get_json(silent=True) or []
    if not isinstance(rows, list):
        abort(400)
    out = {}
    for code in {str(r.get("cde", "")) for r in rows if isinstance(r, dict)}:
        inst = Institute.query.filter_by(code=code).first()
        if not inst:
            out[code] = "unknown"
            continue
        part = []
        for r in rows:
            if isinstance(r, dict) and str(r.get("cde")) == code:
                phone = "".join(ch for ch in str(r.get("phone", "")) if ch.isdigit() or ch == "+")[:20]
                r = dict(r, phone=phone, errors=[] if (r.get("last_name") and r.get("first_name") and len(phone) >= 9) else ["x"])
                part.append(r)
        out[code] = _import(part, inst, source="api")
    return jsonify(out)
