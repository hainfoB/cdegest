from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Wilaya
from ..security import ADMIN, COORD, DFEP, MFEP, RESP, TEACHER, roles_required, visible_institutes, visible_users, visible_wilayas
from ..services.period import training_year

bp = Blueprint("main", __name__)

# KPI catalogue, grouped by family (values computed from étape 4 onward)
KPI_FAMILIES = [
    ("activity", ["groups", "sessions", "trained", "teachers", "hours", "fill"]),
    ("attendance", ["attendance", "dropouts", "dropout_rate", "certificates"]),
    ("conversion", ["accepted", "conversion", "completed"]),
    ("quality", ["satisfaction", "response"]),
]
KPI_ICONS = {
    "groups": "users", "sessions": "layers", "trained": "user-check", "teachers": "briefcase", "hours": "clock",
    "fill": "pie", "attendance": "check", "dropouts": "user-x", "dropout_rate": "trend-down", "certificates": "award",
    "accepted": "thumb", "conversion": "repeat", "completed": "flag", "satisfaction": "smile", "response": "message",
}


@bp.route("/health")
def health():
    db.session.execute(db.text("SELECT 1"))
    return {"status": "ok"}


@bp.route("/")
def home():
    if current_user.is_authenticated and request.args.get("public") != "1":
        return redirect(url_for("main.dashboard"))
    return render_template("public/home.html")


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
    label, _start, _end, quarter = training_year()
    ctx = {
        "year": "\u2066" + label + "\u2069",  # isolate LTR inside RTL text
        "quarter": quarter,
        "families": KPI_FAMILIES,
        "icons": KPI_ICONS,
    }
    if u.role in (ADMIN, MFEP):
        ctx["view"] = "national"
        ctx["wilayas"] = visible_wilayas(u).all()
    elif u.role in (DFEP, COORD):
        ctx["view"] = "wilaya"
    elif u.role == RESP:
        ctx["view"] = "institute"
    else:
        ctx["view"] = "teacher"
    if u.role != TEACHER:
        ctx["institutes"] = visible_institutes(u).all()
        ctx["accounts"] = visible_users(u).filter_by(active=True).count()
        ctx["n_wilayas"] = visible_wilayas(u).count()
    return render_template("dashboard/index.html", **ctx)


@bp.route("/comparaison")
@roles_required(ADMIN, MFEP)
def compare():
    codes = [c for c in request.args.getlist("w") if c][:5]
    wilayas = Wilaya.query.filter(Wilaya.code.in_(codes)).order_by(Wilaya.code).all() if codes else []
    label, _s, _e, quarter = training_year()
    return render_template("dashboard/compare.html", wilayas=wilayas, families=KPI_FAMILIES,
                           icons=KPI_ICONS, year="\u2066" + label + "\u2069", quarter=quarter)
