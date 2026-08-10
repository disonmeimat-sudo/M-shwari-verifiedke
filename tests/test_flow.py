from app.extensions import db
from app.models.loan import LoanApplication
from app.models.payment import PaymentTransaction
from tests.conftest import complete_application, submit_application


def test_landing_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "LOAN PORTAL KE" in html
    assert "Get a Loan" in html
    assert "Apply quickly from your mobile phone." in html
    assert "KES 45,000" in html
    assert "Service fee: KES 800" in html
    assert "Demo" in html


def test_loan_selection(client):
    resp = client.get("/apply?amount=45000")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Complete your application" in html
    assert "KSH 45,000" in html


def test_invalid_loan_amount(client):
    resp = client.get("/apply?amount=12345")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")


def test_application_form_validation(client):
    resp = client.post("/apply?amount=45000", data={
        "full_name": "Test User",
        "phone": "12345",
        "county": "Nairobi",
        "loan_reason": "Business",
    })
    assert resp.status_code == 200
    assert "Please enter a valid Kenyan mobile number." in resp.get_data(as_text=True)


def test_review_page(client):
    url = submit_application(client)
    resp = client.get(url)
    html = resp.get_data(as_text=True)
    assert "Review Your Application" in html
    assert "KES 45,800" in html
    assert "Test User" in html
    assert "+254 712 345 678" in html


def test_application_creation(client):
    submit_application(client)
    with client.application.app_context():
        row = LoanApplication.query.first()
        assert row is not None
        assert row.loan_amount == 45000
        assert row.service_fee == 800
        assert row.total_amount == 45800
        assert row.status == "DRAFT"


def test_payment_initiation(client):
    app_id, tx_id, _ = complete_application(client)
    resp = client.get(f"/payment/{app_id}/{tx_id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Check Your Phone" in html
    assert "KES 45,800" in html
    with client.application.app_context():
        tx = PaymentTransaction.query.get(tx_id)
        assert tx.status == "PENDING"
        assert tx.amount == 45800
        assert LoanApplication.query.get(app_id).status == "PAYMENT_PENDING"


def test_pending_payment(slow_client):
    _, tx_id, _ = complete_application(slow_client)
    resp = slow_client.get(f"/api/payment/{tx_id}/status")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "PENDING"


def test_successful_sandbox_payment(client):
    app_id, tx_id, _ = complete_application(client)
    resp = client.get(f"/api/payment/{tx_id}/status")
    assert resp.get_json()["status"] == "SUCCESS"
    resp = client.get(f"/application/{app_id}/success")
    html = resp.get_data(as_text=True)
    assert "Application Submitted Successfully" in html
    assert "Sandbox transaction" in html
    with client.application.app_context():
        assert LoanApplication.query.get(app_id).status == "PAYMENT_SUCCESS"


def test_failed_sandbox_payment(client):
    app_id, tx_id, _ = complete_application(client)
    resp = client.post(f"/api/payment/{tx_id}/simulate", json={"status": "FAILED"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "FAILED"
    resp = client.get(f"/application/{app_id}/failed")
    assert "Payment Unsuccessful" in resp.get_data(as_text=True)
    with client.application.app_context():
        assert LoanApplication.query.get(app_id).status == "PAYMENT_FAILED"


def test_cancelled_sandbox_payment(client):
    app_id, tx_id, _ = complete_application(client)
    resp = client.post(f"/api/payment/{tx_id}/simulate", json={"status": "CANCELLED"})
    assert resp.status_code == 200
    with client.application.app_context():
        assert LoanApplication.query.get(app_id).status == "PAYMENT_CANCELLED"
    resp = client.get(f"/application/{app_id}/failed")
    assert "Payment Unsuccessful" in resp.get_data(as_text=True)


def test_duplicate_confirmation_guard(client):
    app_id, _, _ = complete_application(client)
    resp = client.post(f"/confirm/{app_id}")
    assert resp.status_code == 302
    assert "/application/" in resp.headers["Location"]


def test_cannot_manipulate_payment_amount(client):
    app_id, tx_id, _ = complete_application(client)
    with client.application.app_context():
        # Amount is always the server-computed total (45,000 + 800), never a client value
        assert PaymentTransaction.query.get(tx_id).amount == 45800
    # Forged transaction IDs are rejected
    assert client.get("/api/payment/999999/status").status_code == 404
    assert client.get(f"/payment/{app_id}/999999").status_code == 404
    # Tampering with the amount query string on a draft does not change it
    resp = client.post("/apply?amount=5000", data={
        "full_name": "Test User",
        "phone": "712345678",
        "county": "Nairobi",
        "loan_reason": "Business",
    })
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    with client.application.app_context():
        row = LoanApplication.query.get(int([p for p in loc.split("/") if p.isdigit()][0]))
        assert row.loan_amount == 5000