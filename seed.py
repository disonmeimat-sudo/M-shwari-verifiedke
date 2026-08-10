"""Seed development data. Usage: python seed.py"""
import os
import sys

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, ".env"))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.settings import SystemSetting  # noqa: E402

DEFAULTS = {
    "disclaimer_text": (
        "LOAN PORTAL KE is an independent application portal. "
        "It is not operated by Safaricom, M-Shwari, or any government agency."
    ),
    "stk_helper_text": (
        "Once you receive an STK push, finish your payment and receive your loan."
    ),
    "applications_today": "—",
}


def seed():
    app = create_app()
    with app.app_context():
        db.create_all()
        for key, value in DEFAULTS.items():
            row = SystemSetting.query.filter_by(key=key).first()
            if row is None:
                db.session.add(SystemSetting(key=key, value=value))
        db.session.commit()
        print(f"Seeded {len(DEFAULTS)} settings.")
        print(f"Loan products available: {len(app.config['LOAN_PRODUCTS'])}")
        print("Lab mode:", app.config["LAB_MODE"])


if __name__ == "__main__":
    seed()