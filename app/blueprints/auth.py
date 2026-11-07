"""Connexion par NIN (CU-01) : NIN + mot de passe, code à usage unique, choix du rôle actif ;
activation d'un compte invité (CU-02) ; mot de passe oublié ; changement de rôle en cours de session."""
import time
from collections import defaultdict, deque
from datetime import timedelta
from urllib.parse import urlparse

from flask import (Blueprint, abort, current_app, flash, make_response, redirect, render_template, request, session,
                   url_for)
from flask_login import current_user, login_required, login_user, logout_user

from .. import nin as NIN
from ..extensions import db
from ..i18n import t
from ..models import AGENT_ROLES, AuditLog, Habilitation, Notification, User
from ..services import otp as OTP
from ..utils import utcnow

bp = Blueprint("auth", __name__)

# Anti brute-force par adresse IP : 8 échecs par 10 minutes (par processus), en plus du verrouillage du compte.
_FAILS = defaultdict(deque)
_WINDOW, _MAX = 600, 8


def _ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()


def _blocked(ip):
    q = _FAILS[ip]
    now = time.time()
    while q and now - q[0] > _WINDOW:
        q.popleft()
    return len(q) >= _MAX


def _safe_next(target):
    if not target:
        return None
    p = urlparse(target)
    return target if not p.netloc and not p.scheme and target.startswith("/") else None


def demo_accounts():
    if not current_app.config["SHOW_DEMO_ACCOUNTS"]:
        return []
    from ..cli import DEMO_USERS
    return [u for u in DEMO_USERS if u["show"]]


def home_for(user):
    return url_for("espace.home") if user.role in ("candidat", "stagiaire") else url_for("main.dashboard")


# ------------------------------------------------------------------ étape 1 : NIN + mot de passe

@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    error = None
    nin = ""
    if request.method == "POST":
        ip = _ip()
        nin = NIN.normalize(request.form.get("nin"))
        if _blocked(ip):
            error = t("login.blocked")
        else:
            user = User.by_nin(nin) if NIN.valid(nin) else None
            if user and user.locked:
                error = t("login.locked")
            elif user and user.check_password(request.form.get("password") or ""):
                if not user.active:
                    error = t("login.inactive")
                elif not user.valid_habilitations():
                    error = t("login.no_role")
                else:
                    user.failed_logins = 0
                    session.clear()
                    session["pre"] = {"uid": user.id, "purpose": "login", "remember": bool(request.form.get("remember")),
                                      "next": _safe_next(request.args.get("next"))}
                    needs_code = bool(user.agent_habilitations()) or not OTP.known_device(user)
                    if needs_code:
                        otp, _c = OTP.issue(user, "login")
                        db.session.commit()
                        if otp is None:
                            error = t("otp.too_many") if user.channels() else t("otp.no_channel")
                            session.pop("pre", None)
                        else:
                            return redirect(url_for("auth.code"))
                    else:
                        db.session.commit()
                        return _finish(user, otp_ok=False)
            else:
                _FAILS[ip].append(time.time())
                if user:
                    user.failed_logins = (user.failed_logins or 0) + 1
                    if user.failed_logins >= 5:
                        user.locked_until, user.failed_logins = utcnow() + timedelta(minutes=15), 0
                        AuditLog.log("login.locked", target=f"user:{user.id}", user=user)
                    db.session.commit()
                error = t("login.error")
    return render_template("auth/login.html", error=error, nin=nin, demo=demo_accounts())


def _pre_user():
    pre = session.get("pre")
    if not pre:
        return None, None
    u = db.session.get(User, pre.get("uid"))
    return (u, pre) if u else (None, None)


def _simulated(user, purpose):
    """Message du code tel qu'il est « reçu » (mode démonstration uniquement)."""
    if not current_app.config.get("SHOW_SIMULATED_MESSAGES"):
        return None
    o = OTP.current(user, purpose)
    if o is None:
        return None
    return Notification.query.filter_by(event_key=f"otp:{o.id}").order_by(Notification.id.desc()).first()


# ------------------------------------------------------------------ étape 2 : code à usage unique

@bp.route("/login/code", methods=["GET", "POST"])
def code():
    user, pre = _pre_user()
    if user is None:
        return redirect(url_for("auth.login"))
    purpose = pre.get("purpose", "login")
    error = None
    if request.method == "POST":
        if request.form.get("action") == "resend":
            otp, _c = OTP.issue(user, purpose, request.form.get("channel"))
            db.session.commit()
            flash(t("otp.resent") if otp else t("otp.too_many"), "ok" if otp else "err")
            return redirect(url_for("auth.code"))
        res = OTP.verify(user, purpose, request.form.get("code"))
        db.session.commit()
        if res == "ok":
            AuditLog.log("otp.ok", target=f"user:{user.id}", details=purpose, user=user)
            db.session.commit()
            if purpose == "activate":
                return _finish_activation(user, pre)
            if purpose == "reset":
                session["pre"] = dict(pre, verified=True)
                return redirect(url_for("auth.reset"))
            new_device = not OTP.known_device(user)
            had_login = user.last_login_at is not None
            resp = _finish(user, otp_ok=True)
            if new_device:
                OTP.remember_device(user, resp)
                if had_login:
                    from ..services.events import security_alert
                    security_alert(user, "new_device")
                db.session.commit()
            return resp
        error = {"bad": t("otp.bad"), "expired": t("otp.expired"), "locked": t("otp.locked")}[res]
    o = OTP.current(user, purpose)
    return render_template("auth/code.html", error=error, otp=o, user=user, purpose=purpose,
                           channels=user.channels(), simulated=_simulated(user, purpose))


def _finish(user, otp_ok):
    """Ouvre la session ; choix du rôle si plusieurs habilitations (RG-35)."""
    pre = session.pop("pre", {}) or {}
    pending = session.pop("pending_hab", None)
    login_user(user, remember=bool(pre.get("remember")))
    session["otp_ok"] = otp_ok
    user.last_login_at = utcnow()
    habs = user.valid_habilitations()
    target = None
    if pending:
        target = next((h for h in habs if h.id == pending), None)
    if target is None and len(habs) == 1:
        target = habs[0]
    if target is None and habs and all(h.role in ("candidat", "stagiaire") for h in habs):
        # candidat et stagiaire mènent au même espace : pas de choix à faire
        target = next((h for h in habs if h.role == "stagiaire"), habs[0])
    if target is not None:
        user.use(target)
        AuditLog.log("login", target=f"user:{user.id}", details=target.role, user=user)
        db.session.commit()
        return make_response(redirect(pre.get("next") or home_for(user)))
    AuditLog.log("login", target=f"user:{user.id}", details="choix du rôle", user=user)
    db.session.commit()
    return make_response(redirect(url_for("auth.choose_role", next=pre.get("next"))))


# ------------------------------------------------------------------ étape 3 : rôle actif

@bp.route("/login/role", methods=["GET", "POST"])
@login_required
def choose_role():
    habs = current_user.valid_habilitations()
    if request.method == "POST":
        return _switch(request.form.get("hab", type=int), habs, "role.choose")
    return render_template("auth/role.html", habs=habs, current=session.get("hab"))


@bp.route("/role", methods=["POST"])
@login_required
def switch_role():
    return _switch(request.form.get("hab", type=int), current_user.valid_habilitations(), "role.switch")


def _switch(hab_id, habs, action):
    h = next((x for x in habs if x.id == hab_id), None)
    if h is None:
        abort(403)
    # passer d'un rôle candidat/stagiaire à un rôle d'agent redemande un code (RG-35)
    if h.role in AGENT_ROLES and not session.get("otp_ok"):
        user = current_user._get_current_object()
        otp, _c = OTP.issue(user, "login")
        db.session.commit()
        if otp is None:
            flash(t("otp.too_many"), "err")
            return redirect(home_for(user))
        logout_user()
        session["pre"] = {"uid": user.id, "purpose": "login", "remember": False, "next": None}
        session["pending_hab"] = h.id
        return redirect(url_for("auth.code"))
    current_user.use(h)
    AuditLog.log(action, target=f"user:{current_user.id}", details=f"{h.role}:{h.institute_id or h.wilaya_id or ''}")
    db.session.commit()
    nxt = _safe_next(request.args.get("next") or request.form.get("next"))
    return redirect(nxt or home_for(current_user))


# ------------------------------------------------------------------ déconnexion

@bp.route("/logout", methods=["POST"])
def logout():
    if current_user.is_authenticated:
        AuditLog.log("logout", target=f"user:{current_user.id}")
        db.session.commit()
    logout_user()
    session.clear()
    flash("ok")
    return redirect(url_for("auth.login"))


# ------------------------------------------------------------------ activation d'un compte invité (CU-02)

def _invited(token):
    u = User.query.filter_by(invite_token=token).first()
    if u is None or u.invite_expires is None or u.invite_expires < utcnow():
        return None
    return u


@bp.route("/activation/<token>", methods=["GET", "POST"])
def activate(token):
    u = _invited(token)
    if u is None:
        return render_template("auth/activate.html", expired=True)
    error = None
    if request.method == "POST":
        f = request.form
        pwd, pwd2 = f.get("password") or "", f.get("password2") or ""
        if len(pwd) < 12 or pwd != pwd2:
            error = t("acc.bad_new")
        elif not f.get("charter"):
            error = t("charter.required")
        else:
            ch = f.get("channel")
            if ch == "whatsapp":
                u.mobile_channel, u.wa_consent_at = "whatsapp", utcnow()
            elif ch == "sms":
                u.mobile_channel = "sms"
            if f.get("phone"):
                u.phone = "".join(c for c in f["phone"] if c.isdigit() or c == "+")[:20]
            u.code_channel = ch if ch in ("email", "sms", "whatsapp") else "email"
            from werkzeug.security import generate_password_hash
            session.clear()
            session["pre"] = {"uid": u.id, "purpose": "activate", "pwd": generate_password_hash(pwd), "token": token}
            otp, _c = OTP.issue(u, "activate", u.code_channel)
            db.session.commit()
            if otp is None:
                error = t("otp.no_channel")
            else:
                return redirect(url_for("auth.code"))
    return render_template("auth/activate.html", u=u, error=error, expired=False,
                           habs=[h for h in u.habilitations if h.status == "pending"])


def _finish_activation(user, pre):
    user.password_hash = pre["pwd"]
    user.charter_at = utcnow()
    user.invite_token, user.invite_expires = None, None
    for h in user.habilitations:
        if h.status == "pending":
            h.status = "active"
    AuditLog.log("account.activate", target=f"user:{user.id}", user=user)
    db.session.commit()
    resp = _finish(user, otp_ok=True)
    OTP.remember_device(user, resp)
    db.session.commit()
    return resp


# ------------------------------------------------------------------ mot de passe oublié

@bp.route("/mot-de-passe-oublie", methods=["GET", "POST"])
def forgot():
    sent = False
    if request.method == "POST":
        if _blocked(_ip()):
            flash(t("login.blocked"), "err")
        else:
            _FAILS[_ip()].append(time.time())          # compte aussi comme tentative, contre l'énumération
            user = User.by_nin(request.form.get("nin"))
            if user and user.active and user.channels():
                session.clear()
                session["pre"] = {"uid": user.id, "purpose": "reset"}
                otp, _c = OTP.issue(user, "reset")
                db.session.commit()
                if otp is not None:
                    return redirect(url_for("auth.code"))
            sent = True                                    # message identique : aucune indication sur l'existence du compte
    return render_template("auth/forgot.html", sent=sent)


@bp.route("/mot-de-passe-oublie/nouveau", methods=["GET", "POST"])
def reset():
    user, pre = _pre_user()
    if user is None or not pre.get("verified") or pre.get("purpose") != "reset":
        return redirect(url_for("auth.forgot"))
    error = None
    if request.method == "POST":
        pwd, pwd2 = request.form.get("password") or "", request.form.get("password2") or ""
        if len(pwd) < (12 if user.agent_habilitations() else 10) or pwd != pwd2:
            error = t("acc.bad_new")
        else:
            user.set_password(pwd)
            user.must_change_password = False
            user.locked_until = None
            from ..services.events import security_alert
            security_alert(user, "password")
            AuditLog.log("password.reset", target=f"user:{user.id}", user=user)
            db.session.commit()
            session.clear()
            flash(t("acc.changed"), "ok")
            return redirect(url_for("auth.login"))
    return render_template("auth/reset.html", error=error)


# ------------------------------------------------------------------ charte (EJ-05)

@bp.route("/charte", methods=["GET", "POST"])
@login_required
def charter():
    if request.method == "POST" and request.form.get("charter"):
        current_user.charter_at = utcnow()
        AuditLog.log("charter.accept", target=f"user:{current_user.id}")
        db.session.commit()
        return redirect(home_for(current_user))
    return render_template("auth/charter.html")
