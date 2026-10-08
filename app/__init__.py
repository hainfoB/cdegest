from datetime import date

from flask import Flask, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .extensions import csrf, db, login_manager, migrate


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    migrate.init_app(app, db, compare_type=True)
    login_manager.init_app(app)
    csrf.init_app(app)

    from . import models  # noqa: F401  (register tables)
    from .models import User

    @login_manager.user_loader
    def load_user(uid):
        return db.session.get(User, int(uid))

    from .blueprints.auth import bp as auth_bp
    from .blueprints.main import bp as main_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    from .cli import register_cli
    register_cli(app)

    _register_template_helpers(app)
    _register_security_headers(app)
    _register_errors(app)
    return app


def _register_template_helpers(app):
    from flask_login import current_user

    from .i18n import get_lang, t, text_dir
    from .security import nav_for, scope_label

    @app.context_processor
    def inject():
        lang = get_lang()
        ctx = {"t": t, "lang": lang, "dir": text_dir(), "config": app.config, "today": date.today()}
        if current_user.is_authenticated:
            ctx["nav"] = nav_for(current_user)
            ctx["scope_label"] = scope_label(current_user, lang)
        return ctx

    @app.after_request
    def remember_lang(resp):
        lang = request.args.get("lang")
        if lang in app.config["LANGS"]:
            resp.set_cookie("lang", lang, max_age=3600 * 24 * 365, samesite="Lax")
        return resp


def _register_security_headers(app):
    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(self), geolocation=()")
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
