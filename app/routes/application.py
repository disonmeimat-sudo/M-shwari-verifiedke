from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from flask_wtf import FlaskForm
from wtforms import EmailField, SelectField, StringField, SubmitField
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    Optional,
    ValidationError,
)

from app.extensions import db
from app.models.loan import LoanApplication, Notification
from app.services import loan_service, payment_service
from app.utils import normalize_phone


bp = Blueprint("application", __name__)


# ============================================================
# APPLICATION STATUS CONSTANTS
# ============================================================

DRAFT = "DRAFT"
SUBMITTED = "SUBMITTED"
PAYMENT_PENDING = "PAYMENT_PENDING"
PAYMENT_SUCCESS = "PAYMENT_SUCCESS"
PAYMENT_FAILED = "PAYMENT_FAILED"
PAYMENT_CANCELLED = "PAYMENT_CANCELLED"


# ============================================================
# OWNERSHIP / SESSION HELPERS
# ============================================================

def _get_owned(application_id, *statuses):
    """
    Only allow access to the application belonging
    to the current browser session.
    """

    if session.get("draft_application_id") != application_id:
        return None

    app_obj = LoanApplication.query.get(application_id)

    if app_obj is None:
        return None

    if statuses and app_obj.status not in statuses:
        return None

    return app_obj


def _session_draft():
    """
    Return the current draft application for this session.
    """

    app_id = session.get("draft_application_id")

    if not app_id:
        return None

    try:
        app_id = int(app_id)
    except (TypeError, ValueError):
        return None

    app_obj = LoanApplication.query.get(app_id)

    if app_obj is None:
        return None

    if app_obj.status != DRAFT:
        return None

    return app_obj


# ============================================================
# APPLICATION FORM
# ============================================================

class ApplicationForm(FlaskForm):

    full_name = StringField(
        "Full Legal Name",
        validators=[
            DataRequired(
                "Please enter your full legal name."
            ),
            Length(min=3, max=120),
        ],
    )

    phone = StringField(
        "M-PESA / Mobile Number",
        validators=[
            DataRequired(
                "Please enter your mobile number."
            )
        ],
    )

    county = SelectField(
        "County of Residence",
        validators=[
            DataRequired(
                "Please select your county."
            )
        ],
    )

    loan_reason = SelectField(
        "Reason for Loan",
        validators=[
            DataRequired(
                "Please select a reason for the loan."
            )
        ],
    )

    email = EmailField(
        "Email (optional)",
        validators=[
            Optional(),
            Email(
                "Please enter a valid email address."
            ),
        ],
    )

    submit = SubmitField("Continue")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        from flask import current_app

        self.county.choices = [
            ("", "Select county")
        ] + [
            (county, county)
            for county in current_app.config["COUNTIES"]
        ]

        self.loan_reason.choices = [
            ("", "Select reason")
        ] + [
            (reason, reason)
            for reason in current_app.config["LOAN_REASONS"]
        ]

    def validate_phone(self, field):
        if normalize_phone(field.data) is None:
            raise ValidationError(
                "Please enter a valid Kenyan mobile number."
            )


# ============================================================
# APPLY
# ============================================================

@bp.route("/apply", methods=["GET", "POST"])
def apply():

    # --------------------------------------------------------
    # Never trust the amount supplied by the browser.
    # Validate it against configured loan products.
    # --------------------------------------------------------

    raw_amount = (
        request.args.get("amount")
        or request.form.get("amount")
        or ""
    )

    try:
        amount = int(raw_amount)
    except (TypeError, ValueError):
        amount = 0

    product = loan_service.get_product(amount)

    if product is None:
        flash(
            "Invalid loan amount selected.",
            "error",
        )

        return redirect(
            url_for("main.landing")
        )

    form = ApplicationForm()

    app_obj = _session_draft()

    # --------------------------------------------------------
    # SAVE APPLICATION
    # --------------------------------------------------------

    if form.validate_on_submit():

        # Create a new draft if there isn't a valid one
        # for this loan amount.
        if (
            app_obj is None
            or app_obj.loan_amount != amount
        ):
            app_obj = loan_service.create_draft(amount)

            session["draft_application_id"] = app_obj.id

        # Normalize phone before storing it.
        phone = normalize_phone(form.phone.data)

        loan_service.update_draft(
            app_obj,
            {
                "full_name": form.full_name.data,
                "phone": phone,
                "county": form.county.data,
                "loan_reason": form.loan_reason.data,
                "email": form.email.data or "",
            },
        )

        return redirect(
            url_for(
                "application.review",
                application_id=app_obj.id,
            )
        )

    # --------------------------------------------------------
    # PREFILL FORM WHEN EDITING
    # --------------------------------------------------------

    if (
        app_obj
        and app_obj.loan_amount == amount
        and app_obj.full_name
    ):

        form.full_name.data = app_obj.full_name

        if app_obj.phone:
            form.phone.data = (
                app_obj.phone[3:]
                if len(app_obj.phone) == 12
                else app_obj.phone
            )

        form.county.data = app_obj.county
        form.loan_reason.data = app_obj.loan_reason
        form.email.data = app_obj.email or ""

    return render_template(
        "application.html",
        form=form,
        product=product,
        step=2,
        back_url=url_for("main.landing"),
    )


# ============================================================
# REVIEW
# ============================================================

@bp.route("/review/<int:application_id>")
def review(application_id):

    app_obj = _get_owned(
        application_id,
        DRAFT,
    )

    if app_obj is None:
        abort(404)

    return render_template(
        "review.html",
        application=app_obj,
        step=3,
        back_url=url_for(
            "application.apply",
            amount=app_obj.loan_amount,
        ),
    )


# ============================================================
# CONFIRM APPLICATION
# ============================================================

@bp.route(
    "/confirm/<int:application_id>",
    methods=["GET", "POST"],
)
def confirm(application_id):

    app_obj = _get_owned(
        application_id,
        DRAFT,
        SUBMITTED,
    )

    if app_obj is None:
        abort(404)

    # --------------------------------------------------------
    # POST = CONFIRM APPLICATION
    # --------------------------------------------------------

    if request.method == "POST":

        # Prevent duplicate submission.
        if app_obj.status != DRAFT:

            flash(
                "This application has already been submitted.",
                "error",
            )

            return redirect(
                url_for(
                    "application.detail",
                    application_id=app_obj.id,
                )
            )

        # ----------------------------------------------------
        # Mark application as submitted.
        # ----------------------------------------------------

        app_obj.status = SUBMITTED

        db.session.add(
            Notification(
                application_id=app_obj.id,
                title="Application submitted",
                body=(
                    f"Application "
                    f"{app_obj.application_number} "
                    "submitted, awaiting payment."
                ),
            )
        )

        db.session.commit()

        # ----------------------------------------------------
        # Create pending payment transaction.
        #
        # This does NOT send the STK Push.
        # ----------------------------------------------------

        tx = payment_service.create_pending_payment(
            app_obj
        )

        return redirect(
            url_for(
                "payment.payment_screen",
                application_id=app_obj.id,
                transaction_id=tx.id,
            )
        )

    # --------------------------------------------------------
    # GET = SHOW CONFIRMATION PAGE
    # --------------------------------------------------------

    return render_template(
        "confirm.html",
        application=app_obj,
        step=3,
        back_url=url_for(
            "application.review",
            application_id=app_obj.id,
        ),
    )


# ============================================================
# SUCCESS
# ============================================================

@bp.route(
    "/application/<int:application_id>/success"
)
def success(application_id):

    app_obj = _get_owned(
        application_id,
        PAYMENT_SUCCESS,
    )

    if app_obj is None:
        abort(404)

    return render_template(
        "success.html",
        application=app_obj,
        transaction=app_obj.latest_transaction(),
    )


# ============================================================
# FAILED
# ============================================================

@bp.route(
    "/application/<int:application_id>/failed"
)
def failed(application_id):

    app_obj = _get_owned(
        application_id,
        PAYMENT_FAILED,
        PAYMENT_CANCELLED,
    )

    if app_obj is None:
        abort(404)

    return render_template(
        "failed.html",
        application=app_obj,
        transaction=app_obj.latest_transaction(),
    )


# ============================================================
# APPLICATION DETAIL
# ============================================================

@bp.route(
    "/application/<int:application_id>"
)
def detail(application_id):

    statuses = (
        DRAFT,
        SUBMITTED,
        PAYMENT_PENDING,
        PAYMENT_SUCCESS,
        PAYMENT_FAILED,
        PAYMENT_CANCELLED,
        "UNDER_REVIEW",
        "APPROVED",
        "REJECTED",
        "DISBURSED",
    )

    app_obj = _get_owned(
        application_id,
        *statuses,
    )

    if app_obj is None:
        abort(404)

    return render_template(
        "detail.html",
        application=app_obj,
        transaction=app_obj.latest_transaction(),
    )