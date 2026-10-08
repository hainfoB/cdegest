import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from ..extensions import db
from ..i18n import t
from ..utils import utcnow
from ..models import AuditLog, User

bp = Blueprint("auth", __name__)

# Anti brute-force: max 8 failed attempts per IP per 10 minutes (per process).
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
    if not current_app.config["DEMO_MODE"]:
        return []
    from ..cli import DEMO_USERS
    return [u for u in DEMO_USERS if u["show"]]


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    error = None
    email = ""
    if request.method == "POST":
        ip = _ip()
        email = (request.form.get("email") or "").strip().lower()
        if _blocked(ip):
            error = t("login.blocked")
        else:
            user = User.query.filter_by(email=email).first()
            if user and user.check_password(request.form.get("password") or ""):
                if not user.active:
                    error = t("login.inactive")
                else:
                    login_user(user, remember=bool(request.form.get("remember")))
                    user.last_login_at = utcnow()
                    AuditLog.log("login", target=f"user:{user.id}", user=user)
                    db.session.commit()
                    return redirect(_safe_next(request.args.get("next")) or url_for("main.dashboard"))
            else:
                _FAILS[ip].append(time.time())
                error = t("login.error")
    return render_template("auth/login.html", error=error, email=email, demo=demo_accounts())


@bp.route("/logout", methods=["POST"])
def logout():
    if current_user.is_authenticated:
        AuditLog.log("logout", target=f"user:{current_user.id}")
        db.session.commit()
    logout_user()
    flash("ok")
    return redirect(url_for("auth.login"))
