"""Loan product catalog + draft lifecycle. Amounts are ALWAYS server-side."""
from app.extensions import db
from app.models.loan import LoanApplication


def get_loan_products():
    from flask import current_app
    return current_app.config["LOAN_PRODUCTS"]


def get_product(amount):
    """Return a copy of the product dict or None. Rejects unlisted amounts."""
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return None
    for p in get_loan_products():
        if p["amount"] == amount:
            return dict(p)
    return None


def compute_payment_amount(application):
    """Amount charged through M-Pesa/PalPluss.

    For this loan portal, the borrower pays only the service fee.
    The requested loan amount is NOT charged through the STK push.
    """
    return application.service_fee

def create_draft(amount):
    product = get_product(amount)
    if product is None:
        raise ValueError("Invalid loan amount")
    app_obj = LoanApplication(
        loan_amount=product["amount"],
        service_fee=product["fee"],
        total_amount=product["amount"] + product["fee"],
        full_name="", phone="", county="", loan_reason="",
        status="DRAFT",
    )
    db.session.add(app_obj)
    db.session.commit()
    return app_obj


def update_draft(application, data):
    application.full_name = (data["full_name"] or "").strip().title()
    application.phone = data["phone"]
    application.county = data["county"]
    application.loan_reason = data["loan_reason"]
    application.email = (data.get("email") or "").strip().lower() or None
    application.status = "DRAFT"
    db.session.commit()