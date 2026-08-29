"""Facilitator and discovery-catalogue parsing.

Two ecosystem-level surfaces, neither of which is a single endpoint's 402:

* **Facilitator ``GET /supported``** — the ``{kinds: [...]}`` document a
  facilitator (``x402.org/facilitator``, Coinbase CDP, ...) returns to advertise
  the ``(x402Version, scheme, network)`` triples it can ``verify``/``settle``.
* **Discovery catalogue** — the ``{items: [...]}`` list a facilitator crawls
  from resource servers that embed the ``bazaar`` extension. Coinbase CDP serves
  it at ``/platform/v2/x402/discovery/resources``.

Pure parsing only; network I/O lives in :mod:`x402lint.cli`.
"""

from __future__ import annotations

from typing import Any

from .protocol import _CAIP2, KNOWN_SCHEMES, X402LintError

# Testnet-only, no-auth facilitator — the default for `x402lint facilitator`.
DEFAULT_FACILITATOR = "https://x402.org/facilitator"
# Coinbase CDP discovery catalogue (public; no key needed for read).
DEFAULT_CATALOGUE = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources"

# EVM CAIP-2 ids that have a v1 friendly-name equivalent — the ones the x402.org
# /verify+/settle interop gap (cycle 33) applies to. Mirrors settle.CAIP2_TO_FRIENDLY.
_CAIP2_WITH_FRIENDLY_NAME = {
    "eip155:8453", "eip155:84532", "eip155:43114", "eip155:43113",
    "eip155:137", "eip155:80002",
}


def supported_url(base: str) -> str:
    """Normalise a facilitator base URL to its ``/supported`` endpoint."""
    b = base.rstrip("/")
    return b if b.endswith("/supported") else b + "/supported"


def parse_supported(doc: Any) -> dict[str, Any]:
    """Summarise a facilitator ``/supported`` document.

    Raises :class:`X402LintError` if it is not shaped like one.
    """
    if not isinstance(doc, dict):
        raise X402LintError("/supported response is not a JSON object")
    kinds = doc.get("kinds")
    if not isinstance(kinds, list):
        raise X402LintError("/supported response has no 'kinds' array")

    rows: list[dict[str, Any]] = []
    notes: list[str] = []
    interop: list[str] = []
    caip2_nets: set[str] = set()
    for k in kinds:
        if not isinstance(k, dict):
            notes.append("skipped a non-object entry in 'kinds'")
            continue
        scheme = k.get("scheme")
        network = k.get("network")
        version = k.get("x402Version")
        rows.append({
            "x402Version": version,
            "scheme": scheme,
            "network": network,
            "extra": k.get("extra") or None,
        })
        if isinstance(scheme, str) and scheme and scheme not in KNOWN_SCHEMES:
            notes.append(f"unrecognised scheme {scheme!r} for {network}")
        if version == 2 and not (isinstance(network, str) and _CAIP2.match(network)):
            notes.append(f"v2 kind has non-CAIP-2 network {network!r}")
        if (isinstance(network, str) and _CAIP2.match(network)
                and network in _CAIP2_WITH_FRIENDLY_NAME):
            caip2_nets.add(network)

    if caip2_nets:
        interop.append(
            "/supported advertises EVM network(s) in CAIP-2 form "
            f"({', '.join(sorted(caip2_nets))}); the x402.org facilitator's "
            "/verify + /settle reject these and require the v1 friendly name "
            "(e.g. 'base-sepolia'). Observed 2026-08-29 with a real settlement. "
            "`x402lint roundtrip --facilitator <url>` translates it for you."
        )

    return {
        "kinds": rows,
        "networks": sorted({r["network"] for r in rows if isinstance(r["network"], str)}),
        "schemes": sorted({r["scheme"] for r in rows if isinstance(r["scheme"], str)}),
        "versions": sorted({r["x402Version"] for r in rows
                            if isinstance(r["x402Version"], int)}),
        "extensions": doc.get("extensions") or [],
        "signers": doc.get("signers") or {},
        "notes": notes,
        "interop": interop,
    }


def parse_catalogue(doc: Any) -> list[dict[str, Any]]:
    """Flatten a discovery catalogue ``{items: [...]}`` into resource rows."""
    if not isinstance(doc, dict):
        raise X402LintError("discovery catalogue is not a JSON object")
    items = doc.get("items")
    if not isinstance(items, list):
        raise X402LintError("discovery catalogue has no 'items' array")

    rows: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        accepts = it.get("accepts")
        accepts = accepts if isinstance(accepts, list) else []
        quality = it.get("quality") if isinstance(it.get("quality"), dict) else {}
        method, query = _bazaar_input(it)
        rows.append({
            "resource": it.get("resource"),
            "description": (it.get("description") or "").strip(),
            "x402Version": it.get("x402Version"),
            "n_accepts": len(accepts),
            "networks": sorted({a.get("network") for a in accepts
                                if isinstance(a, dict) and a.get("network")}),
            "schemes": sorted({a.get("scheme") for a in accepts
                               if isinstance(a, dict) and a.get("scheme")}),
            "calls_30d": quality.get("l30DaysTotalCalls"),
            "payers_30d": quality.get("l30DaysUniquePayers"),
            "method": method,
            "query": query,
        })
    return rows


def _bazaar_input(item: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Pull the request method + example query params a resource advertises via
    the ``bazaar`` discovery extension, so a survey can reproduce the call that
    actually triggers the 402. Falls back to ``("GET", {})``."""
    try:
        inp = item["extensions"]["bazaar"]["info"]["input"]
    except (KeyError, TypeError):
        return "GET", {}
    if not isinstance(inp, dict):
        return "GET", {}
    method = inp.get("method")
    method = method.upper() if isinstance(method, str) and method else "GET"
    qp = inp.get("queryParams")
    query = {str(k): str(v) for k, v in qp.items()} if isinstance(qp, dict) else {}
    return method, query


def top_resources(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """The ``limit`` busiest resources with a usable http(s) URL."""
    usable = [r for r in rows
              if isinstance(r["resource"], str)
              and r["resource"].startswith(("http://", "https://"))]
    usable.sort(key=lambda r: (r["calls_30d"] or 0, r["payers_30d"] or 0), reverse=True)
    return usable[:limit]
