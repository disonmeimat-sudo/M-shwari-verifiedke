import os
from datetime import datetime

from flask import Flask, render_template

from config import Config


def create_app(config_class=Config, config_overrides=None):
    app = Flask(
        __name__,
        instance_relative_config=True,
    )

    # ============================================================
    # CONFIGURATION
    # ============================================================

    app.config.from_object(config_class)

    if config_overrides:
        app.config.update(config_overrides)

    # ============================================================
    # VERCEL FILESYSTEM
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
    )

    _ = (loan, payment, settings, user)

    # ============================================================
    # LOGIN MANAGER
    # ============================================================

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return user.User.query.get(int(user_id))
        except (TypeError, ValueError):
            return None

    login_manager.login_view = "main.landing"
    login_manager.login_message = None

    # ============================================================
    # BLUEPRINTS
    # ============================================================

    from app.routes import admin as admin_routes
    from app.routes import application as application_routes
    from app.routes import main as main_routes
    from app.routes import payment as payment_routes

    app.register_blueprint(main_routes.bp)
    app.register_blueprint(application_routes.bp)
    app.register_blueprint(payment_routes.bp)
    app.register_blueprint(admin_routes.bp)

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
    def forbidden(error):
        return render_template(
            "errors/403.html"
        ), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template(
            "errors/404.html"
        ), 404

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()

        return render_template(
            "errors/500.html"
        ), 500

    # ============================================================
    # DATABASE CLI COMMAND
    # ============================================================

    @app.cli.command("init-db")
    def init_db_command():
        """Create database tables."""

        db.create_all()

        print("Database tables created.")

    # ============================================================
    # CREATE ADMIN CLI COMMAND
    # ============================================================

    @app.cli.command("create-admin")
    def create_admin_command():
        """Create an administrator account."""

        import getpass

        from app.models import User

        print()
        print("========================================")
        print("        CREATE ADMINISTRATOR")
        print("========================================")
        print()

        # --------------------------------------------------------
        # ADMIN DETAILS
        # --------------------------------------------------------

        full_name = input(
            "Admin full name: "
        ).strip()

        email = input(
            "Admin email: "
        ).strip()

        password = getpass.getpass(
            "Admin password: "
        )

        confirm_password = getpass.getpass(
            "Confirm password: "
        )

        print()

        # --------------------------------------------------------
        # VALIDATION
        # --------------------------------------------------------

        if not full_name:
            print("Error: Full name is required.")
            return

        if not email:
            print("Error: Email is required.")
            return

        if not password:
            print("Error: Password is required.")
            return

        if password != confirm_password:
            print("Error: Passwords do not match.")
            return

        # --------------------------------------------------------
        # CHECK EXISTING EMAIL
        # --------------------------------------------------------

        existing_email = User.query.filter_by(
            email=email
        ).first()

        if existing_email:
            print(
                "Error: A user with that email already exists."
            )
            return

        # --------------------------------------------------------
        # CREATE ADMIN
        # --------------------------------------------------------

        admin = User(
            full_name=full_name,
            email=email,
            phone=None,
            is_admin=True,
        )

        admin.set_password(password)

        db.session.add(admin)

        # --------------------------------------------------------
        # SAVE
        # --------------------------------------------------------

        try:
            db.session.commit()

        except Exception as error:
            db.session.rollback()

            print(
                "Error: Unable to create administrator."
            )
            print(error)

            return

        # --------------------------------------------------------
        # SUCCESS
        # --------------------------------------------------------

        print()
        print("========================================")
        print("Administrator created successfully.")
        print("========================================")
        print(f"ID:    {admin.id}")
        print(f"Name:  {admin.full_name}")
        print(f"Email: {admin.email}")
        print("Admin: True")
        print("========================================")
        print()

    return app