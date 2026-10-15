from datetime import date

from flask import Flask, g, redirect, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .extensions import csrf, db, login_manager, migrate


def create_app(config_class=Config):
    try:  # .env for local use (created by `flask init-local`)
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    migrate.init_app(app, db, compare_type=True, render_as_batch=True)
    login_manager.init_app(app)
    csrf.init_app(app)

    from . import models  # noqa: F401  (register tables)
    from .models import User

    @login_manager.user_loader
    def load_user(uid):
        return db.session.get(User, int(uid))

    from .blueprints.auth import bp as auth_bp
    from .blueprints.main import bp as main_bp
    from .blueprints.nesda import bp as nesda_bp
    from .blueprints.org import bp as org_bp
    from .blueprints.public import bp as public_bp
    from .blueprints.reports import bp as reports_bp
    from .blueprints.sessions import bp as sessions_bp
    from .blueprints.candidatures import bp as cand_bp
    for b in (auth_bp, main_bp, org_bp, sessions_bp, nesda_bp, public_bp, reports_bp, cand_bp):
        app.register_blueprint(b)

    from .cli import register_cli
    register_cli(app)

    _register_template_helpers(app)
    _register_guards(app)
    _register_security_headers(app)
    _register_errors(app)
    return app


def _register_template_helpers(app):
    from flask_login import current_user

    from .i18n import get_lang, t, text_dir
    from .security import nav_for, scope_label, sees_people
    from .services.kpi import fmt
    from .blueprints.public import qr_svg

    @app.context_processor
    def inject():
        lang = get_lang()
        ctx = {"t": t, "lang": lang, "dir": text_dir(), "config": app.config, "today": date.today(), "fmt": fmt,
               "qr": qr_svg, "arr": "←" if text_dir() == "rtl" else "→",
               "back": "→" if text_dir() == "rtl" else "←"}
        if current_user.is_authenticated:
            ctx["nav"] = nav_for(current_user)
            ctx["scope_label"] = scope_label(current_user, lang)
            ctx["sees_people"] = sees_people(current_user)
        return ctx

    @app.template_filter("d")
    def fmt_date(d):
        return d.strftime("%d/%m/%Y") if d else "—"

    @app.template_filter("dt")
    def fmt_dt(d):
        return d.strftime("%d/%m/%Y %H:%M") if d else "—"

    @app.template_filter("wa")
    def wa_link(phone):
        """WhatsApp link for an Algerian number (0XXXXXXXXX → 213XXXXXXXXX)."""
        digits = "".join(c for c in (phone or "") if c.isdigit())
        if digits.startswith("0"):
            digits = "213" + digits[1:]
        return f"https://wa.me/{digits}" if digits else None

    @app.after_request
    def remember_lang(resp):
        lang = request.args.get("lang")
        if lang in app.config["LANGS"]:
            resp.set_cookie("lang", lang, max_age=3600 * 24 * 365, samesite="Lax")
        return resp


def _register_guards(app):
    from flask_login import current_user

    @app.before_request
    def force_password_change():
        if (current_user.is_authenticated and current_user.must_change_password
                and request.endpoint not in ("org.account", "auth.logout", "static", "main.set_lang")):
            return redirect(url_for("org.account"))


def _register_security_headers(app):
    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(self), geolocation=()")
        if g.get("allow_frame"):
            # embeddable widget for the public CDE site
            resp.headers["Content-Security-Policy"] = f"frame-ancestors 'self' {app.config['PUBLIC_SITE_URL']}"
        else:
            resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        if request.is_secure:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return resp


def _register_errors(app):
    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("error.html", code=403), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404), 404
