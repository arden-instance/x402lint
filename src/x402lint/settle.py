"""Translate a (v2) ``exact`` challenge into the v1 settle envelope a
facilitator's ``/verify`` + ``/settle`` endpoints expect, and read their
replies.

Discovered cycle 33 against ``x402.org/facilitator`` with a real Base-Sepolia
settlement (tx ``0xf9daa78…``): ``/verify`` and ``/settle`` require
``paymentRequirements.network`` to be the **v1 friendly name**
(``"base-sepolia"``) and reject the CAIP-2 form (``"eip155:84532"``) that the
*same* facilitator's ``/supported`` advertises. The envelope also wants
``x402Version: 1`` and a v1 ``maxAmountRequired`` field (not the v2 ``amount``).
So a "v2 wire" challenge and a "v1 settle" envelope coexist and a client has to
translate between them.

Pure: no network I/O. The POSTs live in :mod:`x402lint.cli`.
"""

from __future__ import annotations

from typing import Any

from .pay import _amount
from .protocol import X402LintError

# CAIP-2 id -> v1 friendly network name. Only chains a facilitator plausibly
# settles for the ``exact`` scheme; extend alongside ``pay._CHAIN_IDS``.
CAIP2_TO_FRIENDLY = {
    "eip155:8453": "base",
    "eip155:84532": "base-sepolia",
    "eip155:43114": "avalanche",
    "eip155:43113": "avalanche-fuji",
    "eip155:137": "polygon",
    "eip155:80002": "polygon-amoy",
}


def friendly_network(network: Any) -> str:
    """CAIP-2 or friendly network string -> v1 friendly name.

    A string with no ``:`` is assumed already friendly and passed through. An
    unmapped CAIP-2 id raises rather than guessing.
    """
    if not isinstance(network, str) or not network:
        raise X402LintError(f"network must be a non-empty string, got {network!r}")
    if network in CAIP2_TO_FRIENDLY:
        return CAIP2_TO_FRIENDLY[network]
    if ":" not in network:
        return network
    raise X402LintError(
        f"no v1 friendly-name mapping for CAIP-2 network {network!r}; "
        "the x402.org facilitator only accepts friendly names on /verify+/settle"
    )


def settle_requirements(entry: dict[str, Any], *, resource_url: str) -> dict[str, Any]:
    """Build the v1 ``paymentRequirements`` a facilitator wants, from a
    (possibly v2) ``accepts[]`` entry."""
    pay_to = entry.get("payTo")
    asset = entry.get("asset")
    if not isinstance(pay_to, str) or not pay_to:
        raise X402LintError("accepts entry has no payTo; cannot build settle envelope")
    if not isinstance(asset, str) or not asset:
        raise X402LintError("accepts entry has no asset; cannot build settle envelope")
    mts = entry.get("maxTimeoutSeconds")
    return {
        "scheme": entry.get("scheme", "exact"),
        "network": friendly_network(entry.get("network")),
        "maxAmountRequired": str(_amount(entry)),
        "resource": entry.get("resource") or resource_url,
        "description": entry.get("description") or "",
        "mimeType": entry.get("mimeType") or "",
        "payTo": pay_to,
        "maxTimeoutSeconds": int(mts) if isinstance(mts, (int, float)) and mts > 0 else 600,
        "asset": asset,
        "extra": entry.get("extra") or None,
    }


def settle_payload(prepared: dict[str, Any]) -> dict[str, Any]:
    """The ``paymentPayload`` for the settle envelope: the prepared payment with
    ``x402Version`` forced to 1 and the network rewritten to the friendly name
    (matching ``settle_requirements``)."""
    payload = dict(prepared["payment_payload"])
    payload["x402Version"] = 1
    payload["network"] = friendly_network(payload.get("network"))
    return payload


def build_envelope(prepared: dict[str, Any], entry: dict[str, Any],
                   *, resource_url: str) -> dict[str, Any]:
    """The full body POSTed to both ``/verify`` and ``/settle``."""
    return {
        "x402Version": 1,
        "paymentPayload": settle_payload(prepared),
        "paymentRequirements": settle_requirements(entry, resource_url=resource_url),
    }


def read_verify(doc: Any) -> dict[str, Any]:
    """Normalise a ``/verify`` reply to ``{valid, payer, reason}``."""
    if not isinstance(doc, dict):
        return {"valid": False, "payer": None, "reason": "verify reply was not a JSON object"}
    return {
        "valid": bool(doc.get("isValid")),
        "payer": doc.get("payer"),
        "reason": doc.get("invalidReason") or doc.get("invalidMessage"),
    }


def read_settle(doc: Any) -> dict[str, Any]:
    """Normalise a ``/settle`` reply to ``{settled, transaction, network, payer, reason}``."""
    if not isinstance(doc, dict):
        return {"settled": False, "transaction": None, "network": None,
                "payer": None, "reason": "settle reply was not a JSON object"}
    tx = doc.get("transaction") or doc.get("txHash") or doc.get("transactionHash")
    return {
        "settled": bool(doc.get("success")),
        "transaction": tx,
        "network": doc.get("network"),
        "payer": doc.get("payer"),
        "reason": doc.get("errorReason") or doc.get("error"),
    }
