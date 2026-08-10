from flask import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.extensions import limiter
from app.models.payment import PaymentTransaction
from app.routes.application import _get_owned
from app.services import payment_service


bp = Blueprint("payment", __name__)


def _owned_application(application_id):
    """
    Make sure the current session owns this application.
    """
    app_obj = _get_owned(
        application_id,
        "SUBMITTED",
        "PAYMENT_PENDING",
        "PAYMENT_SUCCESS",
        "PAYMENT_FAILED",
        "PAYMENT_CANCELLED",
    )

    if app_obj is None:
        return None

    return app_obj


def _owned_tx(application_id, transaction_id):
    tx = PaymentTransaction.query.get(transaction_id)

    if tx is None:
        return None

    if tx.application_id != application_id:
        return None

    if session.get("draft_application_id") != application_id:
        return None

    return tx


def _result_redirect(status, application_id):
    if status == payment_service.SUCCESS:
        return url_for(
            "application.success",
            application_id=application_id,
        )

    return url_for(
        "application.failed",
        application_id=application_id,
    )


# ============================================================
# PAYMENT SCREEN
# ============================================================

@bp.route("/payment/<int:application_id>")
def payment_screen(application_id):

    app_obj = _owned_application(application_id)

    if app_obj is None:
        abort(404)

    # If an existing successful payment exists, don't allow
    # another payment to be initiated.
    existing = (
        PaymentTransaction.query
        .filter_by(
            application_id=application_id,
            status=payment_service.SUCCESS,
        )
        .order_by(PaymentTransaction.id.desc())
        .first()
    )

    if existing:
        return redirect(
            url_for(
                "application.success",
                application_id=application_id,
            )
        )

    amount = payment_service.loan_service.compute_payment_amount(
        app_obj
    )

    return render_template(
        "payment.html",
        application=app_obj,
        transaction=None,
        amount=amount,
        step=3,
    )


# ============================================================
# START PAYMENT
# ============================================================

@bp.post("/payment/<int:application_id>/start")
@limiter.limit("5 per minute")
def start_payment(application_id):

    app_obj = _owned_application(application_id)

    if app_obj is None:
        abort(404)

    # Reuse an existing pending transaction if one exists.
    existing = (
        PaymentTransaction.query
        .filter_by(
            application_id=application_id,
            status=payment_service.PENDING,
        )
        .order_by(PaymentTransaction.id.desc())
        .first()
    )

    if existing and existing.reference:
        tx = existing
    else:
        tx = payment_service.start_payment_for_application(
            app_obj
        )

    if tx is None:
        return jsonify({
            "error": "Unable to create payment transaction."
        }), 500

    # PalPluss must return a transaction reference.
    if not tx.reference:
        return jsonify({
            "error": (
                "PalPluss did not return a transaction reference. "
                "Please try again."
            )
        }), 502

    app_obj.status = "PAYMENT_PENDING"

    from app.extensions import db
    db.session.commit()

    return redirect(
        url_for(
            "payment.processing",
            application_id=application_id,
            transaction_id=tx.id,
        )
    )


# ============================================================
# PROCESSING SCREEN
# ============================================================

@bp.route(
    "/processing/<int:application_id>/<int:transaction_id>"
)
def processing(application_id, transaction_id):

    tx = _owned_tx(
        application_id,
        transaction_id,
    )

    if tx is None:
        abort(404)

    if tx.status in payment_service.TERMINAL:
        return redirect(
            _result_redirect(
                tx.status,
                application_id,
            )
        )

    return render_template(
        "processing.html",
        application=tx.application,
        transaction=tx,
        step=3,
    )


# ============================================================
# POLL PAYMENT STATUS
# ============================================================

@bp.get("/api/payment/<int:transaction_id>/status")
def payment_status(transaction_id):

    tx = PaymentTransaction.query.get(transaction_id)

    if tx is None:
        return jsonify({"error": "Not found"}), 404

    if session.get("draft_application_id") != tx.application_id:
        return jsonify({"error": "Not found"}), 404

    status = payment_service.update_from_poll(tx)

    redirect_url = None

    if status in payment_service.TERMINAL:
        redirect_url = _result_redirect(
            status,
            tx.application_id,
        )

    return jsonify({
        "status": status,
        "reference": tx.reference,
        "redirect_url": redirect_url,
    })


# ============================================================
# RETRY PAYMENT
# ============================================================

@bp.post("/payment/<int:application_id>/retry")
@limiter.limit("5 per minute")
def retry(application_id):

    app_obj = _get_owned(
        application_id,
        "PAYMENT_FAILED",
        "PAYMENT_CANCELLED",
    )

    if app_obj is None:
        abort(404)

    # Return to the payment screen.
    # STK is NOT sent until the user clicks CONTINUE.
    return redirect(
        url_for(
            "payment.payment_screen",
            application_id=application_id,
        )
    )