"""Application configuration.

All sensitive/runtime values come from environment variables.
Production payments use PalPluss and real M-Pesa STK Push.
"""

import os

from dotenv import load_dotenv


# ============================================================
# BASE DIRECTORY / ENVIRONMENT
# ============================================================

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))


# ============================================================
# HELPERS
# ============================================================

def _bool(value, default=False):
    if value is None:
        return default

    return str(value).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

class Config:

    # --------------------------------------------------------
    # Security
    # --------------------------------------------------------

    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "dev-only-secret-change-me",
    )

    # --------------------------------------------------------
    # Database
    # --------------------------------------------------------

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    
    if not SQLALCHEMY_DATABASE_URI:
        raise RuntimeError(
            "DATABASE_URL is not configured."
        )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # --------------------------------------------------------
    # Session security
    # --------------------------------------------------------

    SESSION_COOKIE_HTTPONLY = True

    SESSION_COOKIE_SAMESITE = "Lax"

    SESSION_COOKIE_SECURE = _bool(
        os.environ.get("SESSION_COOKIE_SECURE"),
        False,
    )

    REMEMBER_COOKIE_HTTPONLY = True

    PERMANENT_SESSION_LIFETIME = 60 * 60 * 2


    # ========================================================
    # PAYMENT CONFIGURATION
    # ========================================================

    # Real payment mode.
    #
    # There is NO sandbox payment fallback here.
    LAB_MODE = False

    # Payment provider.
    PAYMENT_PROVIDER = os.environ.get(
        "PAYMENT_PROVIDER",
        "palpluss",
    ).strip().lower()

    # IMPORTANT:
    # The customer pays the service fee through STK Push.
    #
    # Example:
    # Loan amount  = KES 7,500
    # Service fee  = KES 250
    # STK amount   = KES 250
    PAYMENT_AMOUNT_MODE = os.environ.get(
        "PAYMENT_AMOUNT_MODE",
        "fee",
    ).strip().lower()


    # ========================================================
    # PALPLUSS
    # ========================================================

    PALPLUSS_API_KEY = os.environ.get(
        "PALPLUSS_API_KEY",
        "",
    ).strip()

    PALPLUSS_BASE_URL = os.environ.get(
        "PALPLUSS_BASE_URL",
        "https://api.palpluss.com/v1",
    ).strip().rstrip("/")

    PALPLUSS_CHANNEL_ID = os.environ.get(
        "PALPLUSS_CHANNEL_ID",
        "",
    ).strip()

    PALPLUSS_CREDENTIAL_ID = os.environ.get(
        "PALPLUSS_CREDENTIAL_ID",
        "",
    ).strip()

    PALPLUSS_CALLBACK_URL = os.environ.get(
        "PALPLUSS_CALLBACK_URL",
        "",
    ).strip()

    PALPLUSS_DEFAULT_ACCOUNT_REFERENCE = os.environ.get(
        "PALPLUSS_DEFAULT_ACCOUNT_REFERENCE",
        "PAYMENT",
    ).strip()

    PALPLUSS_DEFAULT_TRANSACTION_DESC = os.environ.get(
        "PALPLUSS_DEFAULT_TRANSACTION_DESC",
        "Loan payment",
    ).strip()


    # ========================================================
    # LEGACY M-PESA SETTINGS
    # ========================================================
    #
    # These are retained so that any older code importing them
    # does not immediately break.
    #
    # They are NOT used by the PalPluss payment provider.

    M_PESA_ENV = os.environ.get(
        "M_PESA_ENV",
        "production",
    ).strip().lower()

    PAYMENT_CONSUMER_KEY = os.environ.get(
        "PAYMENT_CONSUMER_KEY",
        "",
    )

    PAYMENT_CONSUMER_SECRET = os.environ.get(
        "PAYMENT_CONSUMER_SECRET",
        "",
    )

    PAYMENT_PASSKEY = os.environ.get(
        "PAYMENT_PASSKEY",
        "",
    )

    PAYMENT_SHORTCODE = os.environ.get(
        "PAYMENT_SHORTCODE",
        "",
    )


    # ========================================================
    # RATE LIMITING
    # ========================================================

    RATELIMIT_DEFAULT = os.environ.get(
        "RATELIMIT_DEFAULT",
        "60 per minute",
    )

    RATELIMIT_STORAGE_URI = os.environ.get(
        "RATELIMIT_STORAGE_URI",
        "memory://",
    )

    RATELIMIT_ENABLED = _bool(
        os.environ.get("RATELIMIT_ENABLED"),
        True,
    )


    # ========================================================
    # LOAN PRODUCTS
    # ========================================================
    #
    # Single source of truth for loan amounts and service fees.
    #
    # NEVER trust loan amounts coming from the browser.
    # The server determines the actual product.

    LOAN_PRODUCTS = [
        {"amount": 5000, "fee": 200},
        {"amount": 7500, "fee": 250},
        {"amount": 10000, "fee": 300},
        {"amount": 12500, "fee": 350},
        {"amount": 16000, "fee": 450},
        {"amount": 21000, "fee": 500},
        {"amount": 25500, "fee": 650},
        {"amount": 30000, "fee": 600},
        {"amount": 35000, "fee": 650},
        {"amount": 40000, "fee": 750},
        {"amount": 45000, "fee": 800},
        {"amount": 50000, "fee": 900},
        {"amount": 60000, "fee": 1050},
        {"amount": 70000, "fee": 1200},
        {"amount": 80000, "fee": 1350},
        {"amount": 100000, "fee": 1650},
    ]


    # ========================================================
    # KENYAN COUNTIES
    # ========================================================

    COUNTIES = [
        "Baringo",
        "Bomet",
        "Bungoma",
        "Busia",
        "Elgeyo-Marakwet",
        "Embu",
        "Garissa",
        "Homa Bay",
        "Isiolo",
        "Kajiado",
        "Kakamega",
        "Kericho",
        "Kiambu",
        "Kilifi",
        "Kirinyaga",
        "Kisii",
        "Kisumu",
        "Kitui",
        "Kwale",
        "Laikipia",
        "Lamu",
        "Machakos",
        "Makueni",
        "Mandera",
        "Marsabit",
        "Meru",
        "Migori",
        "Mombasa",
        "Murang'a",
        "Nairobi",
        "Nakuru",
        "Nandi",
        "Narok",
        "Nyamira",
        "Nyandarua",
        "Nyeri",
        "Samburu",
        "Siaya",
        "Taita-Taveta",
        "Tana River",
        "Tharaka-Nithi",
        "Trans Nzoia",
        "Turkana",
        "Uasin Gishu",
        "Vihiga",
        "Wajir",
        "West Pokot",
    ]


    # ========================================================
    # LOAN REASONS
    # ========================================================

    LOAN_REASONS = [
        "Business",
        "Education",
        "Emergency",
        "Medical",
        "Agriculture",
        "Personal",
        "Rent",
        "School Fees",
        "Other",
        "Fundraising",
    ]


    # ========================================================
    # USER-FACING TEXT
    # ========================================================

    DISCLAIMER_TEXT = os.environ.get(
        "DISCLAIMER_TEXT",
        (
            "Please review all application details carefully "
            "This is done in empowerment of youths ad future generation"
        ),
    )

    STK_HELPER_TEXT = os.environ.get(
        "STK_HELPER_TEXT",
        (
            "Once you receive an STK Push on your M-Pesa phone, "
            "enter your M-Pesa PIN to complete the service fee "
            "payment."
        ),
    )