"""Payment provider abstraction.

LAB_MODE=true            -> SandboxProvider simulates the STK push lifecycle.
PAYMENT_PROVIDER=mpesa   -> MpesaProvider talks to Safaricom Daraja.

Credentials always come from environment variables, never from source code.
"""
import base64
import json
import secrets
from datetime import datetime

import requests

from app.extensions import db
from app.models.payment import PaymentTransaction
from app.services import loan_service

PENDING = "PENDING"
SUCCESS = "SUCCESS"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
TIMEOUT = "TIMEOUT"

TERMINAL = {SUCCESS, FAILED, CANCELLED, TIMEOUT}


class PaymentProviderError(Exception):
    pass


class BaseProvider:
    name = "base"

    def initiate(self, application, phone, amount, reference=None):
        raise NotImplementedError

    def check_status(self, transaction):
        raise NotImplementedError


class SandboxProvider(BaseProvider):
    """Simulates the STK push. Auto-succeeds after a configurable delay."""

    name = "sandbox"

    def __init__(self, app):
        self.app = app

    def initiate(self, application, phone, amount, reference=None):
        ref = reference or f"SANDBOX-{secrets.token_hex(6).upper()}"
        tx = PaymentTransaction(
            application_id=application.id,
            phone=phone,
            amount=amount,
            provider=self.name,
            reference=ref,
            status=PENDING,
            meta_data=json.dumps({
                "lab": True,
                "initiated_at": datetime.utcnow().isoformat(),
                "success_delay": self.app.config["SANDBOX_SUCCESS_DELAY"],
            }),
        )
        db.session.add(tx)
        return tx

    def check_status(self, transaction):
        if transaction.status != PENDING:
            return transaction.status
        meta = json.loads(transaction.meta_data or "{}")
        started = datetime.fromisoformat(
            meta.get("initiated_at", datetime.utcnow().isoformat())
        )
        delay = self.app.config["SANDBOX_SUCCESS_DELAY"]
        if (datetime.utcnow() - started).total_seconds() >= delay:
            return SUCCESS
        return PENDING


class MpesaProvider(BaseProvider):
    """Real Daraja STK push. Only used when LAB_MODE=false + credentials set."""

    name = "mpesa"
    SANDBOX_BASE = "https://sandbox.safaricom.co.ke"
    LIVE_BASE = "https://api.safaricom.co.ke"

    def __init__(self, app):
        self.app = app
        self._token = None
        self._token_expiry = 0

    @property
    def base_url(self):
        env = self.app.config["M_PESA_ENV"]
        return self.LIVE_BASE if env == "production" else self.SANDBOX_BASE

    def _access_token(self):
        if self._token and datetime.utcnow().timestamp() < self._token_expiry - 60:
            return self._token
        key = self.app.config["PAYMENT_CONSUMER_KEY"]
        secret = self.app.config["PAYMENT_CONSUMER_SECRET"]
        if not key or not secret:
            raise PaymentProviderError("M-Pesa credentials are not configured.")
        resp = requests.get(
            f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials",
            auth=(key, secret), timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = datetime.utcnow().timestamp() + int(
            data.get("expires_in", 3599)
        )
        return self._token

    def _password(self):
        cfg = self.app.config
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        raw = f"{cfg['PAYMENT_SHORTCODE']}{cfg['PAYMENT_PASSKEY']}{ts}"
        return base64.b64encode(raw.encode()).decode(), ts

    def initiate(self, application, phone, amount, reference=None):
        cfg = self.app.config
        password, ts = self._password()
        payload = {
            "BusinessShortCode": cfg["PAYMENT_SHORTCODE"],
            "Password": password,
            "Timestamp": ts,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": cfg["PAYMENT_SHORTCODE"],
            "PhoneNumber": phone,
            "CallBackURL": cfg.get("PAYMENT_CALLBACK_URL", ""),
            "AccountReference": application.application_number,
            "TransactionDesc": f"Loan application {application.application_number}",
        }
        resp = requests.post(
            f"{self.base_url}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers={"Authorization": f"Bearer {self._access_token()}"},
            timeout=15,
        )
        if resp.status_code != 200:
            raise PaymentProviderError(f"STK push request failed: HTTP {resp.status_code}")
        data = resp.json()
        if data.get("ResponseCode") != "0":
            raise PaymentProviderError(
                f"STK push rejected: {data.get('ResponseDescription')}"
            )
        tx = PaymentTransaction(
            application_id=application.id,
            phone=phone,
            amount=amount,
            provider=self.name,
            reference=data.get("CheckoutRequestID"),
            status=PENDING,
            meta_data=json.dumps({"request_id": data.get("MerchantRequestID", "")}),
        )
        db.session.add(tx)
        return tx

    def check_status(self, transaction):
        if transaction.status != PENDING:
            return transaction.status
        cfg = self.app.config
        password, ts = self._password()
        payload = {
            "BusinessShortCode": cfg["PAYMENT_SHORTCODE"],
            "Password": password,
            "Timestamp": ts,
            "CheckoutRequestID": transaction.reference,
        }
        resp = requests.post(
            f"{self.base_url}/mpesa/stkpushquery/v1/query",
            json=payload,
            headers={"Authorization": f"Bearer {self._access_token()}"},
            timeout=15,
        )
        data = resp.json()
        code = str(data.get("ResultCode", ""))
        if code == "0":
            return SUCCESS
        if code == "1032":   # user cancelled
            return CANCELLED
        if code == "1037":   # request timed out
            return TIMEOUT
        if code in ("1", "2", "2001", "2002"):
            return FAILED
        return PENDING


def get_provider():
    from flask import current_app
    if current_app.config["LAB_MODE"] or current_app.config["PAYMENT_PROVIDER"] != "mpesa":
        return SandboxProvider(current_app)
    return MpesaProvider(current_app)


def create_payment(application, phone):
    """Amount is ALWAYS recomputed server-side, never taken from the client."""
    amount = loan_service.compute_payment_amount(application)
    provider = get_provider()
    try:
        tx = provider.initiate(application, phone, amount)
    except PaymentProviderError as exc:
        tx = PaymentTransaction(
            application_id=application.id,
            phone=phone,
            amount=amount,
            provider=provider.name,
            status=FAILED,
            meta_data=json.dumps({"error": str(exc)}),
        )
        db.session.add(tx)
        db.session.commit()
        return tx
    db.session.commit()
    return tx


def start_payment_for_application(app_obj):
    """Create a transaction (or reuse an existing PENDING one). Returns (tx, created)."""
    active = PaymentTransaction.query.filter_by(
        application_id=app_obj.id, status=PENDING
    ).first()
    if active:
        return active, False
    tx = create_payment(app_obj, app_obj.phone)
    app_obj.status = "PAYMENT_PENDING"
    db.session.commit()
    return tx, True


def record_outcome(transaction, status, reference=None):
    """Backend-controlled status transition (provider callback / lab simulate)."""
    from app.models.loan import LoanApplication
    transaction.status = status
    if reference:
        transaction.reference = reference
    app_obj = LoanApplication.query.get(transaction.application_id)
    mapping = {
        SUCCESS: "PAYMENT_SUCCESS",
        FAILED: "PAYMENT_FAILED",
        CANCELLED: "PAYMENT_CANCELLED",
        TIMEOUT: "PAYMENT_FAILED",
    }
    if status in mapping:
        app_obj.status = mapping[status]
    db.session.commit()
    return app_obj


def update_from_poll(transaction):
    """Ask the provider for the current state and persist any transition."""
    if transaction.status in TERMINAL:
        return transaction.status
    provider = get_provider()
    status = provider.check_status(transaction)
    if status != transaction.status:
        record_outcome(transaction, status)
    return transaction.status