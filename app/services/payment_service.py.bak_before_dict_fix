"""PalPluss payment provider integration.

Payment flow:

1. Application is submitted.
2. A PENDING payment transaction is prepared.
3. User sees the payment screen.
4. User clicks CONTINUE.
5. PalPluss STK Push is sent.
6. The processing page polls PalPluss.
7. SUCCESS / FAILED / CANCELLED / TIMEOUT is persisted.

IMPORTANT:
- Payment amounts are calculated server-side.
- No browser-supplied amount is trusted.
- PalPluss transaction IDs are stored in PaymentTransaction.reference.
- Provider is always reported as "palpluss".
- Preparing a payment does NOT send an STK Push.
"""

import json
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.models.payment import PaymentTransaction
from app.services import loan_service


# ============================================================
# PALPLUSS IMPORT
# ============================================================

try:
    from palpluss import PalPluss
except ImportError:
    PalPluss = None


# ============================================================
# PAYMENT STATES
# ============================================================

PENDING = "PENDING"
SUCCESS = "SUCCESS"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
TIMEOUT = "TIMEOUT"

TERMINAL = {
    SUCCESS,
    FAILED,
    CANCELLED,
    TIMEOUT,
}


# ============================================================
# EXCEPTIONS
# ============================================================

class PaymentProviderError(Exception):
    """Raised when the payment provider cannot process a request."""

    pass


# ============================================================
# BASE PROVIDER
# ============================================================

class BaseProvider:
    name = "base"

    def initiate(
        self,
        application,
        phone,
        amount,
        reference=None,
    ):
        raise NotImplementedError

    def check_status(self, transaction):
        raise NotImplementedError


# ============================================================
# PALPLUSS PROVIDER
# ============================================================

class PalPlussProvider(BaseProvider):
    """Real M-Pesa STK Push provider using PalPluss."""

    name = "palpluss"

    def __init__(self, app):
        self.app = app

        self.api_key = app.config.get("PALPLUSS_API_KEY")
        self.channel_id = app.config.get("PALPLUSS_CHANNEL_ID")
        self.credential_id = app.config.get("PALPLUSS_CREDENTIAL_ID")
        self.callback_url = app.config.get("PALPLUSS_CALLBACK_URL")

        if not self.api_key:
            raise PaymentProviderError(
                "PalPluss API key is not configured."
            )

        if PalPluss is None:
            raise PaymentProviderError(
                "The palpluss Python package is not installed."
            )

    # ========================================================
    # CLIENT
    # ========================================================

    def _client(self):
        """Create a PalPluss client."""

        return PalPluss(
            api_key=self.api_key
        )

    # ========================================================
    # PHONE NORMALIZATION
    # ========================================================

    def _normalize_phone(self, phone):
        """
        Convert Kenyan mobile numbers to:

            2547XXXXXXXX

        Examples:

            0700123456      -> 254700123456
            0712345678      -> 254712345678
            +254712345678   -> 254712345678
            254712345678    -> 254712345678
        """

        if not phone:
            raise PaymentProviderError(
                "A valid phone number is required."
            )

        phone = (
            str(phone)
            .strip()
            .replace(" ", "")
            .replace("-", "")
        )

        if phone.startswith("+"):
            phone = phone[1:]

        if phone.startswith("0"):
            phone = "254" + phone[1:]

        if not phone.startswith("254"):
            raise PaymentProviderError(
                "Phone number must be a valid Kenyan M-Pesa number."
            )

        if not phone.isdigit() or len(phone) != 12:
            raise PaymentProviderError(
                "Invalid Kenyan phone number format."
            )

        if not phone.startswith(("2547", "2541")):
            raise PaymentProviderError(
                "Phone number is not a supported Kenyan mobile number."
            )

        return phone

    # ========================================================
    # PROVIDER STATUS MAPPING
    # ========================================================

    @staticmethod
    def _map_provider_status(provider_status):
        """Convert PalPluss status into our application status."""

        status = str(
            provider_status or PENDING
        ).upper()

        if status in {
            "SUCCESS",
            "COMPLETED",
            "PAID",
        }:
            return SUCCESS

        if status in {
            "FAILED",
            "FAILURE",
            "REJECTED",
        }:
            return FAILED

        if status in {
            "CANCELLED",
            "CANCELED",
        }:
            return CANCELLED

        if status in {
            "TIMEOUT",
            "TIMED_OUT",
            "EXPIRED",
        }:
            return TIMEOUT

        return PENDING

    # ========================================================
    # INITIATE STK PUSH
    # ========================================================

    def initiate(
        self,
        application,
        phone,
        amount,
        reference=None,
    ):
        """
        Send the actual M-Pesa STK Push through PalPluss.

        This method is called ONLY after the user clicks
        CONTINUE on the payment screen.
        """

        phone = self._normalize_phone(phone)

        try:
            amount = int(amount)
        except (TypeError, ValueError) as exc:
            raise PaymentProviderError(
                "Payment amount must be a valid number."
            ) from exc

        if amount <= 0:
            raise PaymentProviderError(
                "Payment amount must be greater than zero."
            )

        # ----------------------------------------------------
        # Account reference
        # ----------------------------------------------------

        account_reference = (
            reference
            or getattr(
                application,
                "application_number",
                None,
            )
            or f"LOAN-{application.id}"
        )

        transaction_desc = (
            f"Loan application {account_reference}"
        )

        # ----------------------------------------------------
        # Build STK request
        # ----------------------------------------------------

        stk_kwargs = {
            "amount": amount,
            "phone": phone,
            "account_reference": account_reference,
            "transaction_desc": transaction_desc,
        }

        if self.channel_id:
            stk_kwargs["channel_id"] = self.channel_id

        if self.credential_id:
            stk_kwargs["credential_id"] = self.credential_id

        if self.callback_url:
            stk_kwargs["callback_url"] = self.callback_url

        # ----------------------------------------------------
        # Send STK Push
        # ----------------------------------------------------

        try:
            with self._client() as client:
                result = client.stk_push(**stk_kwargs)

        except Exception as exc:
            raise PaymentProviderError(
                f"PalPluss STK Push failed: {str(exc)}"
            ) from exc

        # ----------------------------------------------------
        # Validate response
        # ----------------------------------------------------

        if not result:
            raise PaymentProviderError(
                "PalPluss returned an empty response."
            )

        transaction_id = (
            result.get("transactionId")
            or result.get("transaction_id")
            or result.get("id")
        )

        if not transaction_id:
            raise PaymentProviderError(
                "PalPluss did not return a transaction ID."
            )

        provider_status = str(
            result.get("status", PENDING)
        ).upper()

        local_status = self._map_provider_status(
            provider_status
        )

        return {
            "transaction_id": str(transaction_id),
            "status": local_status,
            "provider_status": provider_status,
            "response": result,
            "phone": phone,
            "amount": amount,
            "account_reference": account_reference,
        }

    # ========================================================
    # CHECK TRANSACTION STATUS
    # ========================================================

    def check_status(self, transaction):
        """
        Retrieve the current transaction status from PalPluss.
        """

        if transaction.status in TERMINAL:
            return transaction.status

        if not transaction.reference:
            # No provider transaction ID yet means the STK
            # has not successfully been initiated.
            return PENDING

        try:
            with self._client() as client:
                result = client.get_transaction(
                    transaction.reference
                )

        except Exception as exc:
            raise PaymentProviderError(
                f"Unable to check PalPluss transaction status: "
                f"{str(exc)}"
            ) from exc

        if not result:
            return PENDING

        provider_status = str(
            result.get("status", PENDING)
        ).upper()

        return self._map_provider_status(
            provider_status
        )


# ============================================================
# PROVIDER SELECTION
# ============================================================

def get_provider():
    """
    Return the configured payment provider.

    This application uses PalPluss only.
    """

    app = current_app

    provider_name = str(
        app.config.get(
            "PAYMENT_PROVIDER",
            "palpluss",
        )
    ).lower()

    if provider_name != "palpluss":
        raise PaymentProviderError(
            "Unsupported payment provider. "
            "Set PAYMENT_PROVIDER=palpluss."
        )

    return PalPlussProvider(app)


# ============================================================
# CALCULATE PAYMENT AMOUNT
# ============================================================

def _payment_amount(application):
    """
    Calculate the payment amount server-side.

    Never trust an amount supplied by the browser.
    """

    amount = loan_service.compute_payment_amount(
        application
    )

    try:
        amount = int(amount)
    except (TypeError, ValueError) as exc:
        raise PaymentProviderError(
            "Unable to calculate payment amount."
        ) from exc

    if amount <= 0:
        raise PaymentProviderError(
            "Payment amount must be greater than zero."
        )

    return amount


# ============================================================
# PREPARE PAYMENT
# ============================================================

def prepare_payment(app_obj):
    """
    Create a PENDING payment transaction.

    IMPORTANT:
    This function DOES NOT send an STK Push.

    The user will first see the payment screen.
    The STK Push is sent only when the user clicks CONTINUE.
    """

    # Reuse an existing pending transaction.
    active = PaymentTransaction.query.filter_by(
        application_id=app_obj.id,
        status=PENDING,
    ).order_by(
        PaymentTransaction.id.desc()
    ).first()

    if active:
        return active

    amount = _payment_amount(app_obj)

    phone = app_obj.phone

    if not phone:
        raise PaymentProviderError(
            "Application does not contain a phone number."
        )

    tx = PaymentTransaction(
        application_id=app_obj.id,
        phone=phone,
        amount=amount,
        provider="palpluss",
        status=PENDING,
        reference=None,
        meta_data=json.dumps(
            {
                "prepared": True,
                "stk_sent": False,
                "created_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            },
            default=str,
        ),
    )

    db.session.add(tx)

    app_obj.status = "PAYMENT_PENDING"

    db.session.commit()

    return tx


# ============================================================
# INITIATE PAYMENT FOR EXISTING TRANSACTION
# ============================================================

def initiate_payment(transaction):
    """
    Send the actual STK Push for an already prepared payment.

    This function is called when the user clicks CONTINUE.
    """

    # --------------------------------------------------------
    # Already successful
    # --------------------------------------------------------

    if transaction.status == SUCCESS:
        return transaction

    # --------------------------------------------------------
    # Don't retry terminal failures here.
    # --------------------------------------------------------

    if transaction.status in {
        FAILED,
        CANCELLED,
        TIMEOUT,
    }:
        raise PaymentProviderError(
            "This payment transaction is no longer active."
        )

    # --------------------------------------------------------
    # Prevent duplicate STK pushes.
    # --------------------------------------------------------

    if transaction.reference:
        return transaction

    application = transaction.application

    if application is None:
        raise PaymentProviderError(
            "Payment application could not be found."
        )

    provider = get_provider()

    try:
        result = provider.initiate(
            application=application,
            phone=transaction.phone,
            amount=transaction.amount,
            reference=(
                getattr(
                    application,
                    "application_number",
                    None,
                )
                or f"LOAN-{application.id}"
            ),
        )

        transaction.reference = result["transaction_id"]
        transaction.status = result["status"]

        metadata = {
            "provider": "palpluss",
            "stk_sent": True,
            "provider_status": result["provider_status"],
            "account_reference": result["account_reference"],
            "initiated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "palpluss_response": result["response"],
        }

        transaction.meta_data = json.dumps(
            metadata,
            default=str,
        )

        # Application status is controlled by payment state.
        if transaction.status == SUCCESS:
            application.status = "PAYMENT_SUCCESS"

        elif transaction.status in {
            FAILED,
            CANCELLED,
            TIMEOUT,
        }:
            application.status = "PAYMENT_FAILED"

        else:
            application.status = "PAYMENT_PENDING"

        db.session.commit()

        return transaction

    except PaymentProviderError as exc:
        db.session.rollback()

        # Re-load the transaction after rollback.
        tx = PaymentTransaction.query.get(
            transaction.id
        )

        if tx is None:
            raise

        tx.status = FAILED

        tx.meta_data = json.dumps(
            {
                "provider": "palpluss",
                "stk_sent": False,
                "error": str(exc),
                "failed_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            },
            default=str,
        )

        application = tx.application

        if application:
            application.status = "PAYMENT_FAILED"

        db.session.commit()

        return tx

    except Exception as exc:
        db.session.rollback()

        tx = PaymentTransaction.query.get(
            transaction.id
        )

        if tx is None:
            raise

        tx.status = FAILED

        tx.meta_data = json.dumps(
            {
                "provider": "palpluss",
                "stk_sent": False,
                "error": "Unexpected payment error.",
                "failed_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            },
            default=str,
        )

        application = tx.application

        if application:
            application.status = "PAYMENT_FAILED"

        db.session.commit()

        return tx


# ============================================================
# BACKWARD-COMPATIBILITY HELPER
# ============================================================

def create_pending_payment(app_obj):
    """
    Backward-compatible alias for prepare_payment().
    """

    return prepare_payment(app_obj)

def prepare_payment(app_obj):
    """
    Prepare a payment transaction WITHOUT sending
    the PalPluss STK Push.

    The STK Push will only be sent when the user
    clicks CONTINUE.
    """

    active = PaymentTransaction.query.filter_by(
        application_id=app_obj.id,
        status=PENDING,
    ).first()

    if active:
        return active

    amount = loan_service.compute_payment_amount(
        app_obj
    )

    tx = PaymentTransaction(
        application_id=app_obj.id,
        phone=app_obj.phone,
        amount=amount,
        provider="palpluss",
        status=PENDING,
        reference=None,
        meta_data=json.dumps({
            "prepared": True,
            "created_at": datetime.utcnow().isoformat(),
        }),
    )

    db.session.add(tx)

    app_obj.status = "PAYMENT_PENDING"

    db.session.commit()

    return tx


def initiate_pending_payment(transaction):
    """
    Send the actual PalPluss STK Push for a prepared transaction.

    IMPORTANT:
    A provider timeout does NOT automatically mean that the STK Push
    failed. The request may have reached PalPluss and the STK may
    already be on the customer's phone.

    Therefore:
        - confirmed provider rejection -> FAILED
        - uncertain/network timeout -> remain PENDING
        - successful initiation -> PENDING/SUCCESS
    """

    if transaction.status in TERMINAL:
        return transaction

    # --------------------------------------------------------
    # Prevent duplicate STK Pushes
    # --------------------------------------------------------

    if transaction.reference:
        return transaction

    from app.models.loan import LoanApplication

    application = LoanApplication.query.get(
        transaction.application_id
    )

    if application is None:
        raise PaymentProviderError(
            "Loan application could not be found."
        )

    provider = get_provider()

    try:
        result_tx = provider.initiate(
            application=application,
            phone=transaction.phone,
            amount=transaction.amount,
        )

        # ----------------------------------------------------
        # Provider accepted the request
        # ----------------------------------------------------

        transaction.reference = result_tx.reference
        transaction.status = result_tx.status
        transaction.meta_data = result_tx.meta_data

        if transaction.status == PENDING:
            application.status = "PAYMENT_PENDING"

        elif transaction.status == SUCCESS:
            application.status = "PAYMENT_SUCCESS"

        elif transaction.status == CANCELLED:
            application.status = "PAYMENT_CANCELLED"

        else:
            application.status = "PAYMENT_FAILED"

        db.session.commit()

        return transaction

    except PaymentProviderError as exc:

        db.session.rollback()

        error_text = str(exc).lower()

        # ----------------------------------------------------
        # PROVIDER TIMEOUT / NETWORK ERROR
        # ----------------------------------------------------
        #
        # We cannot know whether PalPluss received the request.
        #
        # DO NOT mark the transaction FAILED.
        #
        # The STK may already have been sent.
        # ----------------------------------------------------

        uncertain_errors = (
            "timeout",
            "timed out",
            "read timeout",
            "connect timeout",
            "connection timeout",
            "connection reset",
            "connection aborted",
            "connection error",
            "network error",
            "temporarily unavailable",
            "temporary failure",
            "gateway timeout",
            "504",
        )

        if any(
            message in error_text
            for message in uncertain_errors
        ):
            transaction.status = PENDING
            application.status = "PAYMENT_PENDING"

            db.session.commit()

            current_app.logger.warning(
                "PalPluss response timed out/was uncertain "
                "for transaction %s. Keeping transaction PENDING. "
                "The STK Push may already have reached the phone. "
                "Provider error: %s",
                transaction.id,
                exc,
            )

            return transaction

        # ----------------------------------------------------
        # DEFINITE PROVIDER FAILURE
        # ----------------------------------------------------

        transaction.status = FAILED
        application.status = "PAYMENT_FAILED"

        db.session.commit()

        raise

    except Exception as exc:

        db.session.rollback()

        error_text = str(exc).lower()

        # ----------------------------------------------------
        # Unknown network/timeout problem.
        #
        # Do NOT immediately tell the customer the payment
        # failed because the STK request may have reached
        # PalPluss already.
        # ----------------------------------------------------

        uncertain_errors = (
            "timeout",
            "timed out",
            "connection",
            "network",
            "gateway",
            "temporarily unavailable",
        )

        if any(
            message in error_text
            for message in uncertain_errors
        ):
            transaction.status = PENDING
            application.status = "PAYMENT_PENDING"

            db.session.commit()

            current_app.logger.warning(
                "Uncertain PalPluss response for transaction %s: %s",
                transaction.id,
                exc,
            )

            return transaction

        # ----------------------------------------------------
        # Genuine unexpected error
        # ----------------------------------------------------

        transaction.status = FAILED
        application.status = "PAYMENT_FAILED"

        db.session.commit()

        raise PaymentProviderError(
            f"Unable to initiate payment: {str(exc)}"
        ) from exc
        
# ============================================================
# START PAYMENT FOR APPLICATION
# ============================================================

def start_payment_for_application(app_obj):
    """
    Prepare a payment without sending the STK Push.

    Returns:
        (transaction, created)

    IMPORTANT:
    Despite the historical function name, this function now
    only prepares the transaction.

    The actual STK Push is sent by initiate_payment().
    """

    active = PaymentTransaction.query.filter_by(
        application_id=app_obj.id,
        status=PENDING,
    ).order_by(
        PaymentTransaction.id.desc()
    ).first()

    if active:
        return active, False

    tx = prepare_payment(app_obj)

    return tx, True


# ============================================================
# RECORD PAYMENT OUTCOME
# ============================================================

def record_outcome(
    transaction,
    status,
    reference=None,
):
    """
    Persist a backend-controlled payment status transition.
    """

    status = str(status).upper()

    if status not in {
        PENDING,
        SUCCESS,
        FAILED,
        CANCELLED,
        TIMEOUT,
    }:
        raise PaymentProviderError(
            f"Invalid payment status: {status}"
        )

    transaction.status = status

    if reference:
        transaction.reference = reference

    application = transaction.application

    if application is None:
        raise PaymentProviderError(
            "Loan application associated with payment "
            "could not be found."
        )

    # --------------------------------------------------------
    # Update application status
    # --------------------------------------------------------

    if status == SUCCESS:
        application.status = "PAYMENT_SUCCESS"

    elif status == FAILED:
        application.status = "PAYMENT_FAILED"

    elif status == CANCELLED:
        application.status = "PAYMENT_CANCELLED"

    elif status == TIMEOUT:
        application.status = "PAYMENT_FAILED"

    elif status == PENDING:
        application.status = "PAYMENT_PENDING"

    db.session.commit()

    return application


# ============================================================
# POLL PAYMENT STATUS
# ============================================================

def update_from_poll(transaction):
    """
    Ask PalPluss for the current transaction status
    and persist any transition.
    """

    # --------------------------------------------------------
    # Do not poll terminal transactions.
    # --------------------------------------------------------

    if transaction.status in TERMINAL:
        return transaction.status

    # --------------------------------------------------------
    # If STK has not yet been initiated, remain pending.
    # --------------------------------------------------------

    if not transaction.reference:
        return PENDING

    try:
        provider = get_provider()

        status = provider.check_status(
            transaction
        )

    except PaymentProviderError:
        # Temporary provider/API problem.
        # Keep the current status instead of failing the page.
        return transaction.status

    # --------------------------------------------------------
    # Persist status transition.
    # --------------------------------------------------------

    if status != transaction.status:

        record_outcome(
            transaction,
            status,
        )

    return transaction.status