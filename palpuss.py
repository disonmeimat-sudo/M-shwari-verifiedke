#!/usr/bin/env python3
"""
palpuss.py — Palpluss M-Pesa STK Push client.

Wraps the Palpluss Developer API (https://docs.palpluss.com):
    POST /v1/payments/stk            Initiate an STK Push
    GET  /v1/transactions/{id}       Get transaction status
    GET  /v1/transactions            List/filter transactions
    GET  /v1/wallets/service/balance Service wallet balance

Auth: HTTP Basic. The API key goes in the username field with an empty
password. Docs send the raw key directly ("Authorization: Basic pk_...");
if that is rejected with INVALID_API_KEY we retry once with base64(key:).

Statuses: PENDING, PROCESSING, SUCCESS, FAILED, CANCELLED, EXPIRED, REVERSED.

Usage:
    python palpuss.py stk --phone 0712345678 --amount 1000 \
        --reference INV-001 --desc Payment --wait
    python palpuss.py status <transaction_id>
    python palpuss.py poll <transaction_id>
    python palpuss.py balance
    python palpuss.py list --status SUCCESS
    python palpuss.py webhook --port 8000
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import sys
import time
from typing import Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv()  # reads .env; real environment variables take precedence

log = logging.getLogger("palpuss")

# ---------------------------------------------------------------- config ---
API_KEY = os.getenv("PALPLUSS_API_KEY", "").strip()
BASE_URL = os.getenv("PALPLUSS_BASE_URL", "https://api.palpluss.com/v1").rstrip("/")
CALLBACK_URL = os.getenv("PALPLUSS_CALLBACK_URL", "").strip()
CHANNEL_ID = os.getenv("PALPLUSS_CHANNEL_ID", "").strip() or None
DEFAULT_REFERENCE = os.getenv("PALPLUSS_DEFAULT_ACCOUNT_REFERENCE", "PAYMENT")
DEFAULT_DESC = os.getenv("PALPLUSS_DEFAULT_TRANSACTION_DESC", "Payment")

TERMINAL_STATUSES = {"SUCCESS", "FAILED", "CANCELLED", "EXPIRED", "REVERSED"}
POLLING_STATUSES = {"PENDING", "PROCESSING"}

_PHONE_RE = re.compile(r"^(?:\+?254|0)([17]\d{8})$")


def normalize_phone(phone: str) -> str:
    """Accept 07XXXXXXXX / 01XXXXXXXX / +254XXXXXXXXX / 254XXXXXXXXX -> 254XXXXXXXXX."""
    m = _PHONE_RE.match(str(phone).strip())
    if not m:
        raise ValueError(
            f"Invalid Safaricom phone number {phone!r}; "
            "use 07XXXXXXXX, 01XXXXXXXX, +254XXXXXXXXX or 254XXXXXXXXX"
        )
    return "254" + m.group(1)


# ----------------------------------------------------------------- errors ---
class PalplussError(Exception):
    """Raised when the Palpluss API returns an error envelope."""

    def __init__(self, message: str, code: str = None, details: dict = None,
                 request_id: str = None, http_status: int = None,
                 retry_after: str = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.request_id = request_id
        self.http_status = http_status
        self.retry_after = retry_after

    def __str__(self) -> str:
        parts = [self.message]
        if self.code:
            parts.append(f"[{self.code}]")
        if self.details:
            parts.append(f"details={self.details}")
        if self.request_id:
            parts.append(f"(requestId={self.request_id})")
        return " ".join(parts)


class PalplussRateLimitError(PalplussError):
    """429 — global rate limit or STK_TEMP_BANNED abuse protection."""


# ----------------------------------------------------------------- client ---
class PalplussClient:
    def __init__(self, api_key: str = None, base_url: str = None,
                 timeout: int = 9):
        self.api_key = (api_key or API_KEY).strip()
        if not self.api_key:
            raise ValueError("PALPLUSS_API_KEY is not set (check .env)")
        self.base_url = (base_url or BASE_URL).rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Basic {self.api_key}",  # raw key form
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    # -- low level ---------------------------------------------------------
    def _send(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        for attempt in range(2):
            resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
            try:
                body = resp.json()
            except ValueError:
                body = {}
            if (
                attempt == 0
                and resp.status_code == 401
                and isinstance(body, dict)
                and (body.get("error") or {}).get("code") == "INVALID_API_KEY"
                and self.session.headers["Authorization"] == f"Basic {self.api_key}"
            ):
                log.warning("Raw-key auth rejected; retrying with base64(key:)")
                encoded = base64.b64encode(f"{self.api_key}:".encode()).decode()
                self.session.headers["Authorization"] = f"Basic {encoded}"
                continue
            return resp, body
        raise PalplussError("Auth retry exhausted")  # pragma: no cover

    def _request(self, method: str, path: str, **kwargs) -> dict:
        resp, body = self._send(method, path, **kwargs)

        if resp.status_code >= 400:
            error = body.get("error", {}) if isinstance(body, dict) else {}
            exc_type = PalplussRateLimitError if resp.status_code == 429 else PalplussError
            raise exc_type(
                error.get("message", f"HTTP {resp.status_code}"),
                code=error.get("code", "HTTP_ERROR"),
                details=error.get("details", {}),
                request_id=body.get("requestId") if isinstance(body, dict) else None,
                http_status=resp.status_code,
                retry_after=resp.headers.get("Retry-After"),
            )

        if not isinstance(body, dict) or body.get("success") is not True:
            raise PalplussError("Malformed API response", details=body,
                                http_status=resp.status_code)

        return body.get("data", {})

    # -- STK push ----------------------------------------------------------
    def initiate_stk(
        self,
        phone: str,
        amount: float,
        account_reference: str = None,
        transaction_desc: str = None,
        callback_url: str = None,
        channel_id: str = None,
        credential_id: str = None,
    ) -> dict:
        """Trigger an M-Pesa STK Push. Returns the created transaction (PENDING)."""
        if amount is None or float(amount) < 1:
            raise ValueError("amount must be >= 1 KES")

        reference = (account_reference or DEFAULT_REFERENCE)[:12]
        desc = (transaction_desc or DEFAULT_DESC)[:13]
        if len(reference) > 12:
            log.warning("accountReference truncated to 12 chars: %r", reference)
        if len(desc) > 13:
            log.warning("transactionDesc truncated to 13 chars: %r", desc)

        callback = callback_url or CALLBACK_URL
        if not callback.lower().startswith("https://"):
            raise ValueError(
                "callbackUrl must be a public HTTPS URL "
                "(Palpluss requires one per request)"
            )

        payload = {
            "phone": normalize_phone(phone),
            "amount": float(amount),
            "accountReference": reference,
            "transactionDesc": desc,
            "callbackUrl": callback,
        }
        if channel_id or CHANNEL_ID:
            payload["channelId"] = channel_id or CHANNEL_ID
        if credential_id:
            payload["credential_id"] = credential_id

        return self._request("POST", "/payments/stk", json=payload)

    # -- transactions ------------------------------------------------------
    def get_transaction(self, transaction_id: str) -> dict:
        """Fetch one transaction by ID."""
        return self._request("GET", f"/transactions/{transaction_id}")

    def list_transactions(self, status: str = None, type_: str = None,
                          limit: int = 20, cursor: str = None) -> dict:
        """Newest-first page. Returns data with items[], nextCursor, overview."""
        params: dict[str, Any] = {"limit": max(1, min(100, limit))}
        if status:
            params["status"] = status
        if type_:
            params["type"] = type_
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", "/transactions", params=params)

    # -- wallet ------------------------------------------------------------
    def get_wallet_balance(self) -> dict:
        """Service wallet balance (fees are deducted from this wallet)."""
        return self._request("GET", "/wallets/service/balance")

    # -- polling -----------------------------------------------------------
    def wait_for_terminal(self, transaction_id: str, initial_delay: int = 15,
                          poll_interval: int = 10, max_wait: int = 300) -> dict:
        """Poll per the docs: wait 15s, poll every 10s, stop at a terminal
        state, treat as likely failed after 5 minutes."""
        deadline = time.monotonic() + max_wait
        if initial_delay:
            time.sleep(min(initial_delay, max_wait))
        while time.monotonic() < deadline:
            tx = self.get_transaction(transaction_id)
            status = tx.get("status")
            log.info("transaction=%s status=%s", transaction_id, status)
            if status in TERMINAL_STATUSES:
                return tx
            if status not in POLLING_STATUSES:
                log.warning("Unexpected status %r — returning transaction", status)
                return tx
            time.sleep(poll_interval)
        log.warning("No terminal state after %ss — treating as likely failed", max_wait)
        return self.get_transaction(transaction_id)


# ---------------------------------------------------------------- webhook ---
def serve_webhook(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Minimal webhook receiver for Palpluss callbacks (optional).

    Palpluss POSTs {"event": "transaction.updated", "event_type": ...,
    "transaction": {...}} when a payment settles. Return 2xx to acknowledge —
    anything else triggers their retry schedule (10s, 30s, 1m, 2m, 5m).
    Use transaction.id as the idempotency key: duplicates can arrive.
    """
    try:
        from flask import Flask, request
    except ImportError:
        sys.exit("Flask not installed — run: pip install flask")

    app = Flask(__name__)

    @app.post("/webhooks/palpluss")
    def webhook():
        payload = request.get_json(force=True, silent=True) or {}
        tx = payload.get("transaction", {})
        log.info("webhook event=%s status=%s id=%s",
                 payload.get("event_type"), tx.get("status"), tx.get("id"))
        if tx.get("status") == "SUCCESS":
            log.info("PAID: KES %s from %s ref=%s receipt=%s",
                     tx.get("amount"), tx.get("phone_number"),
                     tx.get("external_reference"), tx.get("mpesa_receipt"))
        elif tx.get("status") in ("FAILED", "CANCELLED", "EXPIRED"):
            log.info("NOT PAID: %s (%s)", tx.get("status"),
                     tx.get("result_desc"))
        # TODO: persist the transaction keyed by tx["id"] here
        return {"received": True}, 200

    print(f"Listening on http://{host}:{port}/webhooks/palpluss "
          "(expose publicly with ngrok/localtunnel — HTTPS is required)")
    app.run(host=host, port=port)


# --------------------------------------------------------------------- CLI ---
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="palpuss",
                                description="Palpluss M-Pesa STK Push client")
    p.add_argument("--verbose", action="store_true", help="debug logging")
    sub = p.add_subparsers(dest="command", required=True)

    stk = sub.add_parser("stk", help="Initiate an STK Push")
    stk.add_argument("--phone", required=True,
                     help="07XXXXXXXX / 01XXXXXXXX / +254XXXXXXXXX / 254XXXXXXXXX")
    stk.add_argument("--amount", type=float, required=True, help="KES amount (>= 1)")
    stk.add_argument("--reference", default=None, help="accountReference (max 12 chars)")
    stk.add_argument("--desc", default=None, help="transactionDesc (max 13 chars)")
    stk.add_argument("--callback", default=None,
                     help="HTTPS callbackUrl (default: PALPLUSS_CALLBACK_URL)")
    stk.add_argument("--channel-id", default=None, help="route via specific channel UUID")
    stk.add_argument("--credential-id", default=None, help="BYOC Daraja credential profile")
    stk.add_argument("--wait", action="store_true",
                     help="poll until a terminal state (webhook-free fallback)")

    status = sub.add_parser("status", help="Get transaction status")
    status.add_argument("transaction_id")

    poll = sub.add_parser("poll", help="Poll until terminal state")
    poll.add_argument("transaction_id")

    lst = sub.add_parser("list", help="List/filter transactions")
    lst.add_argument("--status", choices=sorted(TERMINAL_STATUSES | POLLING_STATUSES))
    lst.add_argument("--type", dest="type_", choices=["STK", "B2C"])
    lst.add_argument("--limit", type=int, default=20)
    lst.add_argument("--cursor", default=None)

    sub.add_parser("balance", help="Get service wallet balance")

    wh = sub.add_parser("webhook", help="Run the optional webhook receiver")
    wh.add_argument("--host", default="0.0.0.0")
    wh.add_argument("--port", type=int, default=8000)

    return p


def main(argv: list[str] = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    client = PalplussClient()
    try:
        if args.command == "stk":
            tx = client.initiate_stk(
                phone=args.phone,
                amount=args.amount,
                account_reference=args.reference,
                transaction_desc=args.desc,
                callback_url=args.callback,
                channel_id=args.channel_id,
                credential_id=args.credential_id,
            )
            print(json.dumps(tx, indent=2))
            log.info("STK prompt sent — save transactionId=%s for status checks",
                     tx.get("transactionId"))
            if args.wait:
                tx = client.wait_for_terminal(tx["transactionId"])
                print(json.dumps(tx, indent=2))

        elif args.command == "status":
            print(json.dumps(client.get_transaction(args.transaction_id), indent=2))

        elif args.command == "poll":
            print(json.dumps(client.wait_for_terminal(args.transaction_id), indent=2))

        elif args.command == "list":
            data = client.list_transactions(status=args.status, type_=args.type_,
                                            limit=args.limit, cursor=args.cursor)
            print(json.dumps(data, indent=2))

        elif args.command == "balance":
            bal = client.get_wallet_balance()
            print(json.dumps(bal, indent=2))
            log.info("Service wallet: KES %s available / KES %s ledger",
                     bal.get("availableBalance"), bal.get("ledgerBalance"))

        elif args.command == "webhook":
            serve_webhook(host=args.host, port=args.port)

    except PalplussError as e:
        log.error("Palpluss API error: %s", e)
        if e.retry_after:
            log.error("Retry-After: %ss", e.retry_after)
        sys.exit(1)
    except (ValueError, requests.RequestException) as e:
        log.error("%s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()