"""Approval tokens: the only way a write tool (submit_proposal, send_message) will act.

When the human approves in the web UI, the API mints an HMAC token bound to (user, operation, payload hash,
expiry). The Marketplace MCP server verifies it before any non-dry-run write. An agent, a prompt injection or
a bug cannot produce a valid token, so "nothing leaves without a human" is enforced in two places: the
LangGraph interrupt AND the tool server.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time


def _secret() -> bytes:
    return (os.getenv("APPROVAL_SECRET") or os.getenv("APP_SECRET_KEY") or "dev-only-approval-secret").encode()


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:32]


def mint(user_id: str, operation: str, payload: dict, ttl_s: int = 86400) -> str:
    body = {"u": user_id, "op": operation, "h": payload_hash(payload), "exp": int(time.time()) + ttl_s}
    raw = json.dumps(body, sort_keys=True).encode()
    sig = hmac.new(_secret(), raw, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(raw).decode() + "." + sig


def verify(token: str | None, user_id: str, operation: str, payload: dict) -> tuple[bool, str]:
    if not token or "." not in token:
        return False, "missing approval token"
    raw_b64, sig = token.rsplit(".", 1)
    try:
        raw = base64.urlsafe_b64decode(raw_b64.encode())
        body = json.loads(raw)
    except Exception:  # noqa: BLE001
        return False, "malformed approval token"
    if not hmac.compare_digest(hmac.new(_secret(), raw, hashlib.sha256).hexdigest(), sig):
        return False, "bad signature"
    if body["exp"] < time.time():
        return False, "approval expired"
    if body["op"] != operation:
        return False, f"token is for {body['op']}, not {operation}"
    if body["u"] != user_id:
        return False, "token belongs to another user"
    if body["h"] != payload_hash(payload):
        return False, "payload changed after approval"
    return True, "ok"
