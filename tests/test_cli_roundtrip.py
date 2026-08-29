"""cmd_roundtrip: sign a payment, resend the request, report settlement. No network."""

from __future__ import annotations

import base64
import json

import pytest

pytest.importorskip("eth_account")

from x402lint import cli

PAYTO = "0x209693Bc6afc0C5328bA36FaF03C514EF312287C"
ASSET = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
KEY = "0x" + "42" * 32

V1_BODY = json.dumps({
    "x402Version": 1,
    "accepts": [{
        "scheme": "exact",
        "network": "base-sepolia",
        "maxAmountRequired": "1000",
        "asset": ASSET,
        "payTo": PAYTO,
        "maxTimeoutSeconds": 60,
        "resource": "https://api.example.com/data",
        "extra": {"name": "USDC", "version": "2"},
    }],
}).encode()


def _args(**kw):
    base = dict(url="https://api.example.com/data", method="GET", accept_index=None,
               key_env="X402LINT_PRIVATE_KEY", x402_version=1, timeout=15.0, json=True,
               facilitator=None)
    base.update(kw)
    return type("A", (), base)


def _seq(monkeypatch, *responses):
    it = iter(responses)
    monkeypatch.setattr(cli, "_fetch", lambda *a, **k: next(it))


def test_roundtrip_settled(monkeypatch, capsys):
    monkeypatch.setenv("X402LINT_PRIVATE_KEY", KEY)
    resp = base64.b64encode(json.dumps({
        "success": True,
        "transaction": "0xabc123",
        "network": "base-sepolia",
        "payer": "0xdead",
    }).encode()).decode()
    _seq(monkeypatch,
         (402, {}, V1_BODY),
         (200, {"X-PAYMENT-RESPONSE": resp}, b'{"ok": true}'))
    rc = cli.cmd_roundtrip(_args())
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["settled"] is True
    assert out["transaction"] == "0xabc123"
    assert out["retry_status"] == 200


def test_roundtrip_insufficient_funds(monkeypatch, capsys):
    monkeypatch.setenv("X402LINT_PRIVATE_KEY", KEY)
    _seq(monkeypatch,
         (402, {}, V1_BODY),
         (402, {}, b'{"error": "insufficient_funds"}'))
    rc = cli.cmd_roundtrip(_args())
    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["settled"] is False
    assert out["reason"] == "insufficient_funds"


def test_roundtrip_success_false_in_header(monkeypatch, capsys):
    monkeypatch.setenv("X402LINT_PRIVATE_KEY", KEY)
    resp = base64.b64encode(json.dumps({
        "success": False,
        "errorReason": "invalid_signature",
    }).encode()).decode()
    _seq(monkeypatch,
         (402, {}, V1_BODY),
         (200, {"X-PAYMENT-RESPONSE": resp}, b"{}"))
    rc = cli.cmd_roundtrip(_args())
    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["settled"] is False
    assert out["reason"] == "invalid_signature"


def test_roundtrip_non_402_errors(monkeypatch, capsys):
    monkeypatch.setenv("X402LINT_PRIVATE_KEY", KEY)
    _seq(monkeypatch, (200, {}, b"{}"))
    assert cli.cmd_roundtrip(_args()) == 2
    assert "expected 402" in capsys.readouterr().err


def test_roundtrip_missing_key_errors(monkeypatch, capsys):
    monkeypatch.delenv("X402LINT_PRIVATE_KEY", raising=False)
    assert cli.cmd_roundtrip(_args()) == 2
    assert "private key not found" in capsys.readouterr().err


# --- roundtrip --facilitator (direct verify + settle) ---------------------

V2_CAIP2_BODY = json.dumps({
    "x402Version": 1,
    "accepts": [{
        "scheme": "exact",
        "network": "eip155:84532",          # CAIP-2 — must be translated for /settle
        "amount": "10000",
        "asset": ASSET,
        "payTo": PAYTO,
        "maxTimeoutSeconds": 60,
        "resource": "https://api.example.com/data",
        "extra": {"name": "USDC", "version": "2"},
    }],
}).encode()


def _posts(monkeypatch, *responses):
    it = iter(responses)
    captured = []

    def fake_post(url, payload, timeout):
        captured.append((url, payload))
        return next(it)

    monkeypatch.setattr(cli, "_post_json", fake_post)
    return captured


def test_roundtrip_facilitator_settles(monkeypatch, capsys):
    monkeypatch.setenv("X402LINT_PRIVATE_KEY", KEY)
    _seq(monkeypatch, (402, {}, V2_CAIP2_BODY))
    posts = _posts(
        monkeypatch,
        (200, {"isValid": True, "payer": "0xc838"}),
        (200, {"success": True, "transaction": "0xf9da", "network": "base-sepolia"}),
    )
    rc = cli.cmd_roundtrip(_args(facilitator="https://x402.org/facilitator"))
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["verified"] is True and out["settled"] is True
    assert out["transaction"] == "0xf9da"
    # CAIP-2 network was translated to the friendly name for the envelope
    assert out["network"] == "base-sepolia"
    assert [u for u, _ in posts] == [
        "https://x402.org/facilitator/verify",
        "https://x402.org/facilitator/settle",
    ]
    assert posts[0][1]["paymentRequirements"]["network"] == "base-sepolia"
    assert posts[0][1]["paymentRequirements"]["maxAmountRequired"] == "10000"
    assert posts[0][1]["paymentPayload"]["x402Version"] == 1


def test_roundtrip_facilitator_verify_rejects_no_settle_call(monkeypatch, capsys):
    monkeypatch.setenv("X402LINT_PRIVATE_KEY", KEY)
    _seq(monkeypatch, (402, {}, V2_CAIP2_BODY))
    posts = _posts(
        monkeypatch,
        (200, {"isValid": False, "invalidReason": "insufficient_funds"}),
    )
    rc = cli.cmd_roundtrip(_args(facilitator="https://x402.org/facilitator"))
    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["verified"] is False and out["settled"] is False
    assert out["reason"] == "insufficient_funds"
    assert len(posts) == 1  # settle not attempted after a failed verify
