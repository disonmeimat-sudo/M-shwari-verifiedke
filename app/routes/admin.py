from functools import wraps

from flask import (
    Blueprint,
    abort,
    redirect,
    render_template,
    request,
    url_for,
    flash,
)
from flask_login import current_user, login_user, logout_user

from app.extensions import db
from app.models import User, LoanApplication, PaymentTransaction


bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(
                url_for("admin.login", next=request.full_path)
            )

        if not current_user.is_admin:
            abort(403)

        return view(*args, **kwargs)

    return wrapped_view


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(
            db.or_(
                User.email == identifier,
                User.phone == identifier,
            )
        ).first()

        if (
            user
            and user.is_admin
            and user.check_password(password)
        ):
            login_user(user)

            next_url = request.args.get("next")

            if next_url and next_url.startswith("/"):
                return redirect(next_url)

            return redirect(url_for("admin.dashboard"))

        flash("Invalid administrator credentials.", "error")

    return render_template("admin/login.html")


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("admin.login"))


@bp.route("/")
@admin_required
def dashboard():
    total_users = User.query.count()
    total_applications = LoanApplication.query.count()
    total_payments = PaymentTransaction.query.count()

    pending_payments = PaymentTransaction.query.filter_by(
        status="PENDING"
    ).count()

    successful_payments = PaymentTransaction.query.filter_by(
        status="SUCCESS"
    ).count()

    failed_payments = PaymentTransaction.query.filter_by(
        status="FAILED"
    ).count()

    recent_users = User.query.order_by(
        User.created_at.desc()
    ).limit(8).all()

    recent_applications = LoanApplication.query.order_by(
        LoanApplication.created_at.desc()
    ).limit(8).all()

    return render_template(
        "admin/dashboard.html",
        total_users=total_users,
        total_applications=total_applications,
        total_payments=total_payments,
        pending_payments=pending_payments,
        successful_payments=successful_payments,
        failed_payments=failed_payments,
        recent_users=recent_users,
        recent_applications=recent_applications,
    )


@bp.route("/users")
@admin_required
def users():
    search = request.args.get("search", "").strip()

    query = User.query

    if search:
        pattern = f"%{search}%"

        query = query.filter(
            db.or_(
                User.full_name.ilike(pattern),
                User.phone.ilike(pattern),
                User.email.ilike(pattern),
            )
        )

    users = query.order_by(
        User.created_at.desc()
    ).all()

    return render_template(
        "admin/users.html",
        users=users,
        search=search,
    )


@bp.route("/users/<int:user_id>")
@admin_required
def user_detail(user_id):
    user = User.query.get_or_404(user_id)

    applications = LoanApplication.query.filter_by(
        user_id=user.id
    ).order_by(
        LoanApplication.created_at.desc()
    ).all()

    payments = PaymentTransaction.query.join(
        LoanApplication
    ).filter(
        LoanApplication.user_id == user.id
    ).order_by(
        PaymentTransaction.created_at.desc()
    ).all()

    return render_template(
        "admin/user_detail.html",
        user=user,
        applications=applications,
        payments=payments,
    )


@bp.route("/applications")
@admin_required
def applications():
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()

    query = LoanApplication.query

    if search:
        pattern = f"%{search}%"

        query = query.filter(
            db.or_(
                LoanApplication.full_name.ilike(pattern),
                LoanApplication.phone.ilike(pattern),
                LoanApplication.email.ilike(pattern),
                LoanApplication.application_number.ilike(pattern),
            )
        )

    if status:
        query = query.filter(
            LoanApplication.status == status
        )

    applications = query.order_by(
        LoanApplication.created_at.desc()
    ).all()

    return render_template(
        "admin/applications.html",
        applications=applications,
        search=search,
        status=status,
    )


@bp.route("/payments")
@admin_required
def payments():
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()

    query = PaymentTransaction.query

    if search:
        pattern = f"%{search}%"

        query = query.filter(
            db.or_(
                PaymentTransaction.phone.ilike(pattern),
                PaymentTransaction.reference.ilike(pattern),
            )
        )

    if status:
        query = query.filter(
            PaymentTransaction.status == status
        )

    payments = query.order_by(
        PaymentTransaction.created_at.desc()
    ).all()

    return render_template(
        "admin/payments.html",
        payments=payments,
        search=search,
        status=status,
    )
