"""Unit tests for the v2-challenge -> v1-settle-envelope translation. No network."""

from __future__ import annotations

import pytest

from x402lint.protocol import X402LintError
from x402lint import settle

PAYTO = "0x209693Bc6afc0C5328bA36FaF03C514EF312287C"
ASSET = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


def test_friendly_network_translates_caip2():
    assert settle.friendly_network("eip155:84532") == "base-sepolia"
    assert settle.friendly_network("eip155:8453") == "base"


def test_friendly_network_passthrough_for_friendly_name():
    assert settle.friendly_network("base-sepolia") == "base-sepolia"


def test_friendly_network_rejects_unmapped_caip2():
    with pytest.raises(X402LintError):
        settle.friendly_network("eip155:1")
    with pytest.raises(X402LintError):
        settle.friendly_network("")


def test_settle_requirements_from_v2_entry():
    entry = {
        "scheme": "exact",
        "network": "eip155:84532",
        "amount": "10000",
        "asset": ASSET,
        "payTo": PAYTO,
        "maxTimeoutSeconds": 60,
        "extra": {"name": "USDC", "version": "2"},
    }
    req = settle.settle_requirements(entry, resource_url="https://api.example.com/x")
    assert req["network"] == "base-sepolia"
    assert req["maxAmountRequired"] == "10000"
    assert req["resource"] == "https://api.example.com/x"
    assert req["payTo"] == PAYTO
    assert req["asset"] == ASSET


def test_settle_payload_forces_v1_and_friendly_network():
    prepared = {"payment_payload": {
        "x402Version": 2, "scheme": "exact", "network": "eip155:84532",
        "payload": {"signature": "0xsig", "authorization": {}},
    }}
    p = settle.settle_payload(prepared)
    assert p["x402Version"] == 1
    assert p["network"] == "base-sepolia"
    assert p["payload"]["signature"] == "0xsig"


def test_read_verify_and_settle_replies():
    assert settle.read_verify({"isValid": True, "payer": "0xc838"})["valid"] is True
    assert settle.read_verify({"isValid": False, "invalidReason": "x"})["reason"] == "x"
    assert settle.read_verify("nope")["valid"] is False

    s = settle.read_settle({"success": True, "transaction": "0xf9da", "network": "base-sepolia"})
    assert s["settled"] is True and s["transaction"] == "0xf9da"
    assert settle.read_settle({"success": False, "errorReason": "bad"})["reason"] == "bad"
