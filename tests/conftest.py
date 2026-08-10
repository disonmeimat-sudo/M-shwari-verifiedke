import pytest

from app import create_app
from app.extensions import db as _db


def _make_app(tmp_path, **extra):
    overrides = {
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/test.db",
        "SERVER_NAME": "localhost",
        "LAB_MODE": True,
        "RATELIMIT_ENABLED": False,
        "SANDBOX_SUCCESS_DELAY": 0.0,
    }
    overrides.update(extra)
    return create_app(config_overrides=overrides)


@pytest.fixture()
def app(tmp_path):
    application = _make_app(tmp_path)
    with application.app_context():
        _db.create_all()
    yield application
    with application.app_context():
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def slow_client(tmp_path):
    """Sandbox that stays PENDING (60s delay) — for pending-state tests."""
    application = _make_app(tmp_path, SANDBOX_SUCCESS_DELAY=60.0)
    with application.app_context():
        _db.create_all()
    yield application.test_client()
    with application.app_context():
        _db.drop_all()


def submit_application(client, amount=45000):
    """Valid form POST -> returns /review/<id> location."""
    resp = client.post(
        f"/apply?amount={amount}",
        data={
            "full_name": "Test User",
            "phone": "712345678",
            "county": "Nairobi",
            "loan_reason": "Business",
            "email": "test@example.com",
        },
    )
    assert resp.status_code == 302
    return resp.headers["Location"]


def complete_application(client, amount=45000):
    """Form -> confirm -> returns (app_id, tx_id, payment_url)."""
    review_url = submit_application(client, amount)
    resp = client.post(review_url.replace("/review/", "/confirm/"))
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    ids = [int(p) for p in loc.split("/") if p.isdigit()]
    return ids[0], ids[1], loc