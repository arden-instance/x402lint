"""cmd_pay: fetch a 402, sign an exact-scheme payment, emit the header. No network."""

from __future__ import annotations

import base64
import json

import pytest

pytest.importorskip("eth_account")

from x402lint import cli
from x402lint.protocol import b64json  # noqa: F401  (kept for parity with fixtures)

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

V2_HEADER_DOC = base64.b64encode(json.dumps({
    "x402Version": 2,
    "accepts": [{
        "scheme": "exact",
        "network": "eip155:84532",
        "amount": "2500",
        "asset": ASSET,
        "payTo": PAYTO,
        "maxTimeoutSeconds": 120,
        "extra": {"name": "USDC", "version": "2"},
    }],
}).encode()).decode()


def _args(**kw):
    base = dict(url="https://api.example.com/data", method="GET", accept_index=None,
               key_env="X402LINT_PRIVATE_KEY", x402_version=1, timeout=10.0, json=True)
    base.update(kw)
    return type("A", (), base)


def test_pay_v1_body(monkeypatch, capsys):
    monkeypatch.setenv("X402LINT_PRIVATE_KEY", KEY)
    monkeypatch.setattr(cli, "_fetch", lambda *a, **k: (402, {}, V1_BODY))
    rc = cli.cmd_pay(_args())
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    hdr = json.loads(base64.b64decode(out["header"]))
    assert hdr["x402Version"] == 1
    assert hdr["scheme"] == "exact"
    assert hdr["payload"]["authorization"]["to"] == PAYTO
    assert hdr["payload"]["authorization"]["value"] == "1000"
    assert out["payer"].startswith("0x") and len(out["payer"]) == 42


def test_pay_v2_header(monkeypatch, capsys):
    monkeypatch.setenv("X402LINT_PRIVATE_KEY", KEY)
    monkeypatch.setattr(cli, "_fetch",
                        lambda *a, **k: (402, {"payment-required": V2_HEADER_DOC}, b"{}"))
    rc = cli.cmd_pay(_args(x402_version=2))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    hdr = json.loads(base64.b64decode(out["header"]))
    assert hdr["x402Version"] == 2
    assert hdr["payload"]["authorization"]["value"] == "2500"


def test_pay_non_402_errors(monkeypatch, capsys):
    monkeypatch.setenv("X402LINT_PRIVATE_KEY", KEY)
    monkeypatch.setattr(cli, "_fetch", lambda *a, **k: (200, {}, b"{}"))
    assert cli.cmd_pay(_args()) == 2
    assert "expected 402" in capsys.readouterr().err


def test_pay_missing_key_errors(monkeypatch, capsys):
    monkeypatch.delenv("X402LINT_PRIVATE_KEY", raising=False)
    monkeypatch.setattr(cli, "_fetch", lambda *a, **k: (402, {}, V1_BODY))
    assert cli.cmd_pay(_args()) == 2
    assert "private key not found" in capsys.readouterr().err
