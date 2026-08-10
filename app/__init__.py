import os
from datetime import datetime

from flask import Flask, render_template

from config import Config


def create_app(config_class=Config, config_overrides=None):
    app = Flask(
        __name__,
        instance_relative_config=True,
    )

    app.config.from_object(config_class)

    if config_overrides:
        app.config.update(config_overrides)

    # ============================================================
    # VERCEL FILESYSTEM
    # ============================================================
    # Vercel's deployed filesystem is read-only.
    # /tmp is writable during the function execution.
    # Keep the normal instance directory when running locally.
    # ============================================================

    if os.environ.get("VERCEL"):
        app.instance_path = "/tmp/instance"

    os.makedirs(
        app.instance_path,
        exist_ok=True,
    )

    # ============================================================
    # EXTENSIONS
    # ============================================================

    from app.extensions import (
        csrf,
        db,
        limiter,
        login_manager,
        migrate,
    )

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # ============================================================
    # MODELS
    # ============================================================

    from app.models import (
        loan,
        payment,
        settings,
        user,
    )  # noqa: F401

    # ============================================================
    # LOGIN MANAGER
    # ============================================================

    @login_manager.user_loader
    def load_user(user_id):
        return user.User.query.get(int(user_id))

    login_manager.login_view = "main.landing"
    login_manager.login_message = None

    # ============================================================
    # BLUEPRINTS
    # ============================================================

    from app.routes import application as application_routes
    from app.routes import main as main_routes
    from app.routes import payment as payment_routes

    app.register_blueprint(main_routes.bp)
    app.register_blueprint(application_routes.bp)
    app.register_blueprint(payment_routes.bp)

    # ============================================================
    # TEMPLATE FILTERS
    # ============================================================

    from app.utils import format_ksh, format_phone

    app.template_filter("ksh")(format_ksh)
    app.template_filter("phone")(format_phone)

    # ============================================================
    # GLOBAL TEMPLATE VARIABLES
    # ============================================================

    @app.context_processor
    def inject_globals():
        from app.services.loan_service import get_loan_products
        from app.services.settings_service import get_setting

        return {
            "app_name": "M-SHWARI LOANS",
            "lab_mode": app.config["LAB_MODE"],
            "loan_products": get_loan_products(),
            "disclaimer_text": get_setting(
                "disclaimer_text",
                app.config["DISCLAIMER_TEXT"],
            ),
            "stk_helper_text": get_setting(
                "stk_helper_text",
                app.config["STK_HELPER_TEXT"],
            ),
            "applications_today": get_setting(
                "applications_today",
                "—",
            ),
            "counties": app.config["COUNTIES"],
            "loan_reasons": app.config["LOAN_REASONS"],
            "now": datetime.utcnow(),
        }

    # ============================================================
    # ERROR HANDLERS
    # ============================================================

    @app.errorhandler(403)
    def forbidden(e):
        return render_template(
            "errors/403.html"
        ), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template(
            "errors/404.html"
        ), 404

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()

        return render_template(
            "errors/500.html"
        ), 500

    # ============================================================
    # DATABASE CLI COMMAND
    # ============================================================

    @app.cli.command("init-db")
    def init_db_command():
        db.create_all()
        print("Database tables created.")

    return app