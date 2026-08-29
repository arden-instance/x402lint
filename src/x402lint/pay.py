"""Build and sign an x402 ``exact``-scheme payment for a parsed 402 challenge.

The ``exact`` scheme settles via EIP-3009 ``transferWithAuthorization`` on an
ERC-20 (USDC in practice): the payer signs an EIP-712 ``TransferWithAuthorization``
message off-chain and hands it to the resource server / facilitator, which
submits it on-chain. No gas or on-chain transaction is needed on the payer side
to *produce* the payment — only a signature.

This module is pure and offline: given an ``accepts[]`` entry and a private key
it returns the ``PaymentPayload`` document and the base64 header value a client
would send back. Network settlement (POSTing it and checking the result) is the
job of the ``roundtrip`` command and is deliberately kept separate so the
signing path can be tested with zero I/O.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from typing import Any

from .protocol import X402LintError, b64json, detect_wire_version

# CAIP-2 / friendly-name -> EVM chain id. Extend as needed; unknown -> error.
_CHAIN_IDS = {
    "eip155:8453": 8453, "base": 8453,
    "eip155:84532": 84532, "base-sepolia": 84532,
    "eip155:43114": 43114, "avalanche": 43114,
    "eip155:43113": 43113, "avalanche-fuji": 43113,
    "eip155:137": 137, "polygon": 137,
    "eip155:80002": 80002, "polygon-amoy": 80002,
}

_EVM_ADDR = re.compile(r"^0x[0-9a-fA-F]{40}$")
_UINT = re.compile(r"^(0|[1-9][0-9]*)$")

_EIP712_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ],
}


def challenge_document(status: int, headers: dict[str, str], body: bytes) -> dict[str, Any]:
    """Extract the PaymentRequired document from a fetched 402 response."""
    parsed: Any = None
    if body:
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            parsed = None
    version = detect_wire_version(status, headers, parsed)
    if version == "2":
        blob = {k.lower(): v for k, v in headers.items()}.get("payment-required", "")
        doc = b64json(blob)
    elif version == "1":
        doc = parsed
    else:
        raise X402LintError("response carries no x402 payment challenge")
    if not isinstance(doc, dict) or not isinstance(doc.get("accepts"), list):
        raise X402LintError("challenge document has no accepts[] array")
    return doc


def select_exact_entry(doc: dict[str, Any], index: int | None = None) -> dict[str, Any]:
    """Pick an accepts[] entry to pay: by index, else the first `exact` one."""
    accepts = doc["accepts"]
    if index is not None:
        try:
            return accepts[index]
        except (IndexError, TypeError):
            raise X402LintError(f"no accepts[{index}] entry")
    for entry in accepts:
        if isinstance(entry, dict) and entry.get("scheme") == "exact":
            return entry
    raise X402LintError("no 'exact'-scheme entry in accepts[]; pass --accept-index")


def chain_id_for(network: str) -> int:
    """Resolve an x402 network (CAIP-2 or v1 friendly name) to an EVM chain id."""
    if not isinstance(network, str):
        raise X402LintError(f"network must be a string, got {network!r}")
    if network in _CHAIN_IDS:
        return _CHAIN_IDS[network]
    m = re.match(r"^eip155:(\d+)$", network)
    if m:
        return int(m.group(1))
    raise X402LintError(
        f"unknown network {network!r}; not a known name or 'eip155:<id>' CAIP-2 id"
    )


def _domain_name_version(entry: dict[str, Any]) -> tuple[str, str]:
    """EIP-712 domain name/version for the asset.

    x402 carries these in ``extra`` precisely so clients need not hardcode token
    metadata. USDC uses version ``"2"``; its ``name`` is ``"USDC"`` on most
    testnets and ``"USD Coin"`` on some mainnets, so it must come from the wire.
    """
    extra = entry.get("extra")
    if isinstance(extra, dict) and extra.get("name") and extra.get("version"):
        return str(extra["name"]), str(extra["version"])
    raise X402LintError(
        "accepts entry has no usable extra.{name,version}; cannot build the "
        "EIP-712 domain for the exact scheme (a compliant v2 'exact' offer must "
        "include it)"
    )


def _amount(entry: dict[str, Any]) -> int:
    for key in ("amount", "maxAmountRequired"):
        v = entry.get(key)
        if isinstance(v, str) and _UINT.match(v):
            return int(v)
        if isinstance(v, int) and not isinstance(v, bool):
            return v
    raise X402LintError("accepts entry has no integer amount / maxAmountRequired")


def build_authorization(
    entry: dict[str, Any],
    payer: str,
    *,
    valid_for: int | None = None,
    now: int | None = None,
    nonce: bytes | None = None,
) -> dict[str, str]:
    """Construct the EIP-3009 authorization tuple (all values as strings)."""
    if not _EVM_ADDR.match(payer or ""):
        raise X402LintError(f"payer address is not a 0x+40hex EVM address: {payer!r}")
    pay_to = entry.get("payTo")
    if not (isinstance(pay_to, str) and _EVM_ADDR.match(pay_to)):
        raise X402LintError(f"accepts entry payTo is not an EVM address: {pay_to!r}")

    now = int(time.time()) if now is None else now
    if valid_for is None:
        mts = entry.get("maxTimeoutSeconds")
        valid_for = int(mts) if isinstance(mts, (int, float)) and mts > 0 else 600
    nonce_bytes = os.urandom(32) if nonce is None else nonce
    if len(nonce_bytes) != 32:
        raise X402LintError("nonce must be exactly 32 bytes")

    return {
        "from": payer,
        "to": pay_to,
        "value": str(_amount(entry)),
        "validAfter": "0",
        "validBefore": str(now + int(valid_for)),
        "nonce": "0x" + nonce_bytes.hex(),
    }


def typed_data(entry: dict[str, Any], authorization: dict[str, str]) -> dict[str, Any]:
    """The full EIP-712 payload for signing / inspection."""
    asset = entry.get("asset")
    if not (isinstance(asset, str) and _EVM_ADDR.match(asset)):
        raise X402LintError(f"accepts entry asset is not an EVM address: {asset!r}")
    name, version = _domain_name_version(entry)
    return {
        "types": _EIP712_TYPES,
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name": name,
            "version": version,
            "chainId": chain_id_for(entry.get("network")),
            "verifyingContract": asset,
        },
        "message": {
            "from": authorization["from"],
            "to": authorization["to"],
            "value": int(authorization["value"]),
            "validAfter": int(authorization["validAfter"]),
            "validBefore": int(authorization["validBefore"]),
            "nonce": bytes.fromhex(authorization["nonce"][2:]),
        },
    }


def sign_authorization(td: dict[str, Any], private_key: str) -> str:
    """Sign the EIP-712 typed data, returning a 0x-prefixed 65-byte signature."""
    try:
        from eth_account import Account
        from eth_account.messages import encode_typed_data
    except ModuleNotFoundError as e:  # pragma: no cover - env guard
        raise X402LintError(
            "signing needs the 'eth-account' package (pip install x402lint[pay])"
        ) from e
    signed = Account.sign_message(encode_typed_data(full_message=td), private_key)
    return "0x" + signed.signature.hex()


def payment_payload(
    entry: dict[str, Any],
    authorization: dict[str, str],
    signature: str,
    *,
    x402_version: int = 1,
) -> dict[str, Any]:
    """Assemble the x402 ``PaymentPayload`` document."""
    return {
        "x402Version": x402_version,
        "scheme": entry.get("scheme", "exact"),
        "network": entry.get("network"),
        "payload": {"signature": signature, "authorization": authorization},
    }


def encode_header(payload: dict[str, Any]) -> str:
    """base64 (standard, padded) of the compact JSON — the X-PAYMENT header value."""
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.b64encode(raw).decode()


def prepare_payment(
    entry: dict[str, Any],
    private_key: str,
    *,
    x402_version: int = 1,
    valid_for: int | None = None,
    now: int | None = None,
    nonce: bytes | None = None,
) -> dict[str, Any]:
    """End-to-end offline: entry + key -> authorization, typed data, signature, header.

    Only the ``exact`` scheme is supported; other schemes raise.
    """
    scheme = entry.get("scheme")
    if scheme not in (None, "exact"):
        raise X402LintError(f"only the 'exact' scheme is supported for signing, not {scheme!r}")

    try:
        from eth_account import Account
    except ModuleNotFoundError as e:  # pragma: no cover - env guard
        raise X402LintError(
            "signing needs the 'eth-account' package (pip install x402lint[pay])"
        ) from e
    payer = Account.from_key(private_key).address

    authorization = build_authorization(
        entry, payer, valid_for=valid_for, now=now, nonce=nonce
    )
    td = typed_data(entry, authorization)
    signature = sign_authorization(td, private_key)
    payload = payment_payload(entry, authorization, signature, x402_version=x402_version)
    return {
        "payer": payer,
        "typed_data": td,
        "authorization": authorization,
        "signature": signature,
        "payment_payload": payload,
        "header": encode_header(payload),
    }
