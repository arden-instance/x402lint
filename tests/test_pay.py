"""Offline tests for the exact-scheme signing path (x402lint.pay).

eth-account is a hard dep of the test env; if it is ever made optional these
tests skip rather than fail.
"""

from __future__ import annotations

import base64
import json

import pytest

from x402lint import pay
from x402lint.protocol import X402LintError

eth_account = pytest.importorskip("eth_account")
from eth_account import Account  # noqa: E402
from eth_account.messages import encode_typed_data  # noqa: E402

# Throwaway key — do not fund. Address 0x2e98...  (deterministic).
KEY = "0x" + "42" * 32
PAYER = Account.from_key(KEY).address

V2_ENTRY = {
    "scheme": "exact",
    "network": "eip155:84532",
    "amount": "1000",
    "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    "payTo": "0x209693Bc6afc0C5328bA36FaF03C514EF312287C",
    "maxTimeoutSeconds": 300,
    "extra": {"name": "USDC", "version": "2"},
}
V1_ENTRY = {
    "scheme": "exact",
    "network": "base-sepolia",
    "maxAmountRequired": "1000",
    "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    "payTo": "0x209693Bc6afc0C5328bA36FaF03C514EF312287C",
    "maxTimeoutSeconds": 60,
    "extra": {"name": "USDC", "version": "2"},
}

FIXED_NONCE = bytes(range(32))


def test_chain_id_resolution():
    assert pay.chain_id_for("eip155:84532") == 84532
    assert pay.chain_id_for("base") == 8453
    assert pay.chain_id_for("eip155:12345") == 12345
    with pytest.raises(X402LintError):
        pay.chain_id_for("solana-devnet")
    with pytest.raises(X402LintError):
        pay.chain_id_for(None)


def test_build_authorization_shape():
    auth = pay.build_authorization(V2_ENTRY, PAYER, now=1_000_000, nonce=FIXED_NONCE)
    assert auth["from"] == PAYER
    assert auth["to"] == V2_ENTRY["payTo"]
    assert auth["value"] == "1000"
    assert auth["validAfter"] == "0"
    assert auth["validBefore"] == str(1_000_000 + 300)  # from maxTimeoutSeconds
    assert auth["nonce"] == "0x" + FIXED_NONCE.hex()


def test_v1_amount_key_and_default_timeout():
    entry = dict(V1_ENTRY)
    del entry["maxTimeoutSeconds"]
    auth = pay.build_authorization(entry, PAYER, now=0, nonce=FIXED_NONCE)
    assert auth["value"] == "1000"
    assert auth["validBefore"] == "600"  # 10-minute fallback


def test_missing_extra_is_an_error():
    entry = {k: v for k, v in V2_ENTRY.items() if k != "extra"}
    auth = pay.build_authorization(entry, PAYER, nonce=FIXED_NONCE)
    with pytest.raises(X402LintError, match="EIP-712 domain"):
        pay.typed_data(entry, auth)


def test_bad_addresses_rejected():
    with pytest.raises(X402LintError):
        pay.build_authorization(V2_ENTRY, "0xnope", nonce=FIXED_NONCE)
    bad_payto = dict(V2_ENTRY, payTo="0x1234")
    with pytest.raises(X402LintError):
        pay.build_authorization(bad_payto, PAYER, nonce=FIXED_NONCE)


def test_non_exact_scheme_rejected():
    with pytest.raises(X402LintError, match="exact"):
        pay.prepare_payment(dict(V2_ENTRY, scheme="upto"), KEY)


def test_prepare_payment_roundtrip_signature_recovers():
    out = pay.prepare_payment(V2_ENTRY, KEY, x402_version=2, now=1_700_000_000,
                              nonce=FIXED_NONCE)
    assert out["payer"] == PAYER

    # The signature must recover to the payer over the same typed data.
    recovered = Account.recover_message(
        encode_typed_data(full_message=out["typed_data"]),
        signature=out["signature"],
    )
    assert recovered == PAYER

    # Domain wired from the entry, not hardcoded.
    dom = out["typed_data"]["domain"]
    assert dom["chainId"] == 84532
    assert dom["verifyingContract"] == V2_ENTRY["asset"]
    assert dom["name"] == "USDC" and dom["version"] == "2"


def test_header_is_base64_json_payment_payload():
    out = pay.prepare_payment(V1_ENTRY, KEY, x402_version=1, now=0, nonce=FIXED_NONCE)
    decoded = json.loads(base64.b64decode(out["header"]))
    assert decoded == out["payment_payload"]
    assert decoded["x402Version"] == 1
    assert decoded["scheme"] == "exact"
    assert decoded["payload"]["signature"] == out["signature"]
    assert decoded["payload"]["authorization"]["from"] == PAYER


def test_signature_is_deterministic_for_fixed_inputs():
    a = pay.prepare_payment(V2_ENTRY, KEY, now=42, nonce=FIXED_NONCE)["signature"]
    b = pay.prepare_payment(V2_ENTRY, KEY, now=42, nonce=FIXED_NONCE)["signature"]
    assert a == b
    c = pay.prepare_payment(V2_ENTRY, KEY, now=43, nonce=FIXED_NONCE)["signature"]
    assert a != c  # validBefore changed
