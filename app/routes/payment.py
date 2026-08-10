from flask import (
    Blueprint,
    abort,
    current_app,
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


# ============================================================
# HELPERS
# ============================================================

def _owned_tx(application_id, transaction_id):
    """Return a transaction only if it belongs to the current session/application."""

    tx = PaymentTransaction.query.get(transaction_id)

    if tx is None:
        return None

    if tx.application_id != application_id:
        return None

    if session.get("draft_application_id") != application_id:
        return None

    return tx


def _result_redirect(status, application_id):
    """Return the correct final page for a payment status."""

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

@bp.route(
    "/payment/int:application_id/int:transaction_id",
    methods=["GET"],
)
def payment_screen(application_id, transaction_id):
    """
    Display the payment confirmation screen.

    IMPORTANT:
    This route DOES NOT send the STK Push.

    The STK Push is only sent after the user clicks CONTINUE.
    """

    tx = _owned_tx(application_id, transaction_id)

    if tx is None:
        abort(404)

    # If payment was somehow already completed,
    # do not show the payment screen again.
    if tx.status in payment_service.TERMINAL:
        return redirect(
            _result_redirect(
                tx.status,
                application_id,
            )
        )

    return render_template(
        "payment.html",
        application=tx.application,
        transaction=tx,
        step=3,
    )


# ============================================================
# START STK PUSH
# ============================================================

@bp.post(
    "/payment/int:application_id/int:transaction_id/start",
)
@limiter.limit("5 per minute")
def start_payment(application_id, transaction_id):
    """
    Send the actual PalPluss STK Push.

    This endpoint is called ONLY when the user clicks
    CONTINUE on payment.html.
    """

    tx = _owned_tx(
        application_id,
        transaction_id,
    )

    if tx is None:
        abort(404)

    # --------------------------------------------------------
    # Prevent duplicate STK Pushes
    # --------------------------------------------------------

    if tx.status == payment_service.SUCCESS:
        return jsonify({
            "status": tx.status,
            "redirect_url": _result_redirect(
                tx.status,
                application_id,
            ),
        })

    if tx.status in {
        payment_service.FAILED,
        payment_service.CANCELLED,
        payment_service.TIMEOUT,
    }:
        return jsonify({
            "status": tx.status,
            "redirect_url": _result_redirect(
                tx.status,
                application_id,
            ),
        })

    # --------------------------------------------------------
    # If the transaction already has a PalPluss reference,
    # the STK Push has already been sent.
    # --------------------------------------------------------

    if tx.reference:
        return jsonify({
            "status": tx.status,
            "redirect_url": url_for(
                "payment.processing",
                application_id=application_id,
                transaction_id=tx.id,
            ),
        })

    # --------------------------------------------------------
    # Send STK Push NOW
    # --------------------------------------------------------

    try:
        payment_service.initiate_pending_payment(tx)

    except payment_service.PaymentProviderError as exc:
        current_app.logger.error(
            "PalPluss STK Push failed for transaction %s: %s",
            tx.id,
            exc,
        )

        return jsonify({
            "status": payment_service.FAILED,
            "error": "Unable to send the payment request. Please try again.",
        }), 502

    except Exception:
        current_app.logger.exception(
            "Unexpected error starting payment transaction %s",
            tx.id,
        )

        return jsonify({
            "status": payment_service.FAILED,
            "error": "Unable to start payment. Please try again.",
        }), 500

    # --------------------------------------------------------
    # STK Push was successfully initiated
    # --------------------------------------------------------

    return jsonify({
        "status": tx.status,
        "redirect_url": url_for(
            "payment.processing",
            application_id=application_id,
            transaction_id=tx.id,
        ),
    })


# ============================================================
# PROCESSING SCREEN
# ============================================================

@bp.route(
    "/processing/int:application_id/int:transaction_id",
    methods=["GET"],
)
def processing(application_id, transaction_id):
    """
    Display the processing screen after STK Push has been sent.
    """

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
        poll_url=url_for(
            "payment.payment_status",
            transaction_id=tx.id,
        ),
    )


# ============================================================
# PAYMENT STATUS POLLING
# ============================================================

@bp.get(
    "/api/payment/int:transaction_id/status",
)
def payment_status(transaction_id):
    """
    Poll PalPluss for the current transaction status.
    """

    tx = PaymentTransaction.query.get(transaction_id)

    if tx is None:
        return jsonify({
            "error": "Not found",
        }), 404

    if session.get("draft_application_id") != tx.application_id:
        return jsonify({
            "error": "Not found",
        }), 404

    status = payment_service.update_from_poll(tx)

    redirect_url = None

    if status in payment_service.TERMINAL:
        redirect_url = _result_redirect(
            status,
            tx.application_id,
        )

    return jsonify({
        "status": status,
        "redirect_url": redirect_url,
    })


# ============================================================
# LAB SIMULATION
# ============================================================

@bp.post(
    "/api/payment/int:transaction_id/simulate",
)
@limiter.limit("12 per minute")
def simulate(transaction_id):
    """
    Lab-only payment simulation.
    """

    if not current_app.config.get("LAB_MODE", False):
        abort(403)

    tx = PaymentTransaction.query.get(transaction_id)

    if tx is None:
        return jsonify({
            "error": "Not found",
        }), 404

    if session.get("draft_application_id") != tx.application_id:
        return jsonify({
            "error": "Not found",
        }), 404

    payload = request.get_json(silent=True) or {}

    status = str(
        payload.get("status", "")
    ).upper()

    if status not in payment_service.TERMINAL:
        return jsonify({
            "error": "Invalid status",
        }), 400

    payment_service.record_outcome(
        tx,
        status,
    )

    return jsonify({
        "status": tx.status,
        "redirect_url": _result_redirect(
            tx.status,
            tx.application_id,
        ),
    })


# ============================================================
# RETRY FAILED PAYMENT
# ============================================================

@bp.post(
    "/payment/int:application_id/retry",
)
@limiter.limit("5 per minute")
def retry(application_id):
    """
    Retry a failed/cancelled payment.
    """

    app_obj = _get_owned(
        application_id,
        "PAYMENT_FAILED",
        "PAYMENT_CANCELLED",
    )

    if app_obj is None:
        abort(404)

    tx = payment_service.prepare_payment(
        app_obj
    )

    return redirect(
        url_for(
            "payment.payment_screen",
            application_id=app_obj.id,
            transaction_id=tx.id,
        )
    )