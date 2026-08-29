"""x402 wire-format parsing and conformance rules.

Two wire formats exist in the wild:

* **v2** (``x402Version: 2``) — dominant as of 2026. The ``PaymentRequired``
  document travels base64-encoded in the ``payment-required`` response header;
  the body is an implementation concern (often ``{}`` or a JSON mirror).
  Networks are CAIP-2 ids (``eip155:8453``). The amount field is ``amount``.
* **v1** (``x402Version: 1``) — legacy. The document is the JSON *body* of the
  402 response. Networks are friendly names (``base``). The amount field is
  ``maxAmountRequired`` and each ``accepts[]`` entry carries its own
  ``resource`` URL.

This module is pure: it takes an already-fetched response and returns a
:class:`Report`. Network I/O lives in :mod:`x402lint.cli`.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from typing import Any

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
INFO = "INFO"

# Scheme / network vocabularies. Unknown values warn rather than fail — the
# protocol is deliberately open and new schemes/chains appear regularly.
KNOWN_SCHEMES = {"exact", "upto", "batch-settlement"}
KNOWN_V1_NETWORKS = {
    "base", "base-sepolia", "avalanche", "avalanche-fuji", "iotex",
    "solana", "solana-devnet", "polygon", "polygon-amoy", "sei", "sei-testnet",
}

_EVM_ADDR = re.compile(r"^0x[0-9a-fA-F]{40}$")
_CAIP2 = re.compile(r"^[-a-z0-9]{3,8}:[-_a-zA-Z0-9]{1,32}$")
_UINT = re.compile(r"^(0|[1-9][0-9]*)$")


class X402LintError(Exception):
    """Unrecoverable tool error (bad input, undecodable blob)."""


@dataclass
class Check:
    id: str
    level: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.level:4}  {self.id}: {self.message}"


@dataclass
class Report:
    url: str
    wire_version: str | None = None  # "1", "2", or None if undetected
    checks: list[Check] = field(default_factory=list)

    def add(self, id: str, level: str, message: str) -> None:
        self.checks.append(Check(id, level, message))

    @property
    def failed(self) -> bool:
        return any(c.level == FAIL for c in self.checks)

    @property
    def counts(self) -> dict[str, int]:
        out = {PASS: 0, WARN: 0, FAIL: 0, INFO: 0}
        for c in self.checks:
            out[c.level] = out.get(c.level, 0) + 1
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "wire_version": self.wire_version,
            "ok": not self.failed,
            "counts": self.counts,
            "checks": [vars(c) for c in self.checks],
        }


def b64json(blob: str) -> Any:
    """Decode a base64 (std or url-safe, padded or not) JSON blob."""
    s = blob.strip()
    pad = "=" * (-len(s) % 4)
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            raw = decoder(s + pad)
        except (binascii.Error, ValueError):
            continue
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise X402LintError(f"blob decoded from base64 but is not JSON: {e}")
    raise X402LintError("input is not valid base64")


def classify(doc: Any) -> str:
    """Best-effort label for a decoded x402 document (for `decode`)."""
    if not isinstance(doc, dict):
        return "unknown (not a JSON object)"
    v = doc.get("x402Version")
    if "accepts" in doc and isinstance(doc.get("accepts"), list):
        return f"PaymentRequired / PaymentRequirementsResponse (x402Version={v!r})"
    if "payload" in doc and "scheme" in doc:
        return f"PaymentPayload (x402Version={v!r}, scheme={doc.get('scheme')!r})"
    if "success" in doc:
        return f"SettlementResponse (success={doc.get('success')!r})"
    return f"unknown x402 document (x402Version={v!r})"


def _headers_lower(headers: dict[str, str]) -> dict[str, str]:
    return {k.lower(): v for k, v in headers.items()}


def detect_wire_version(status: int, headers: dict[str, str], body: Any) -> str | None:
    h = _headers_lower(headers)
    if "payment-required" in h:
        return "2"
    if isinstance(body, dict):
        v = body.get("x402Version")
        if v == 1 or (v is None and isinstance(body.get("accepts"), list)):
            return "1"
        if v == 2:
            return "2"
    return None


def _load_document(status: int, headers: dict[str, str], body_bytes: bytes,
                   report: Report) -> Any | None:
    """Return the parsed PaymentRequired doc, appending parse checks."""
    h = _headers_lower(headers)
    body: Any = None
    if body_bytes:
        try:
            body = json.loads(body_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = None

    version = detect_wire_version(status, headers, body)
    report.wire_version = version

    if version == "2":
        report.add("format", INFO, "x402 v2 (payment-required header)")
        blob = h.get("payment-required", "")
        try:
            doc = b64json(blob)
        except X402LintError as e:
            report.add("header-decode", FAIL, f"payment-required header: {e}")
            return None
        report.add("header-decode", PASS, "payment-required header is base64 JSON")
        return doc
    if version == "1":
        report.add("format", INFO, "x402 v1 (JSON body)")
        if not isinstance(body, dict):
            report.add("body-parse", FAIL, "402 body is not a JSON object")
            return None
        report.add("body-parse", PASS, "402 body parses as JSON")
        return body

    report.add(
        "format", FAIL,
        "no x402 payment challenge detected "
        "(no payment-required header, no x402Version in body)",
    )
    return None


def _check_accepts_entry(i: int, entry: Any, version: str, checked_host: str,
                         report: Report) -> None:
    tag = f"accepts[{i}]"
    if not isinstance(entry, dict):
        report.add(tag, FAIL, "entry is not an object")
        return

    amount_key = "amount" if version == "2" else "maxAmountRequired"
    required = ["scheme", "network", amount_key, "asset", "payTo", "maxTimeoutSeconds"]
    missing = [k for k in required if k not in entry]
    if missing:
        report.add(f"{tag}.required", FAIL, f"missing fields: {', '.join(missing)}")
    else:
        report.add(f"{tag}.required", PASS, "all required fields present")

    scheme = entry.get("scheme")
    if scheme in KNOWN_SCHEMES:
        report.add(f"{tag}.scheme", PASS, f"{scheme!r}")
    elif isinstance(scheme, str) and scheme:
        report.add(f"{tag}.scheme", WARN, f"unrecognised scheme {scheme!r}")
    else:
        report.add(f"{tag}.scheme", FAIL, "scheme missing or not a string")

    net = entry.get("network")
    if version == "2":
        if isinstance(net, str) and _CAIP2.match(net):
            report.add(f"{tag}.network", PASS, f"{net} (CAIP-2)")
        else:
            report.add(f"{tag}.network", WARN,
                       f"network {net!r} is not CAIP-2 shaped (expected e.g. 'eip155:8453')")
    else:
        if net in KNOWN_V1_NETWORKS:
            report.add(f"{tag}.network", PASS, f"{net}")
        elif isinstance(net, str) and net:
            report.add(f"{tag}.network", WARN, f"unrecognised v1 network {net!r}")
        else:
            report.add(f"{tag}.network", FAIL, "network missing or not a string")

    amt = entry.get(amount_key)
    if isinstance(amt, str) and _UINT.match(amt) and amt != "0":
        report.add(f"{tag}.{amount_key}", PASS, f"{amt} atomic units")
    else:
        report.add(f"{tag}.{amount_key}", FAIL,
                   f"{amount_key!r} must be a base-10 string of a positive integer, got {amt!r}")

    fam = _network_family(net)
    for addr_key in ("asset", "payTo"):
        val = entry.get(addr_key)
        if fam == "eip155":
            if isinstance(val, str) and _EVM_ADDR.match(val):
                report.add(f"{tag}.{addr_key}", PASS, "valid EVM address")
            else:
                report.add(f"{tag}.{addr_key}", FAIL,
                           f"{addr_key!r} is not a 0x + 40 hex EVM address: {val!r}")
        else:
            if isinstance(val, str) and val:
                report.add(f"{tag}.{addr_key}", INFO,
                           f"{val} (address format not checked for {fam or 'unknown'} networks)")
            else:
                report.add(f"{tag}.{addr_key}", FAIL, f"{addr_key!r} missing or empty")

    to = entry.get("maxTimeoutSeconds")
    if isinstance(to, (int, float)) and not isinstance(to, bool) and to > 0:
        report.add(f"{tag}.maxTimeoutSeconds", PASS, f"{to}")
    else:
        report.add(f"{tag}.maxTimeoutSeconds", FAIL,
                   f"must be a positive number, got {to!r}")

    if scheme == "exact" and fam == "eip155":
        extra = entry.get("extra")
        if isinstance(extra, dict) and extra.get("name") and extra.get("version"):
            report.add(f"{tag}.extra", PASS,
                       f"EIP-712 domain: name={extra['name']!r} version={extra['version']!r}")
        else:
            report.add(f"{tag}.extra", WARN,
                       "exact/EVM needs extra.name + extra.version for the EIP-712 signature")

    res = entry.get("resource")
    if version == "1":
        if isinstance(res, str) and _is_abs_url(res):
            if checked_host and _host(res) and _host(res) != checked_host:
                report.add(f"{tag}.resource", WARN,
                           f"resource host {_host(res)!r} != checked host {checked_host!r}")
            else:
                report.add(f"{tag}.resource", PASS, res)
        else:
            report.add(f"{tag}.resource", FAIL,
                       f"v1 entry must carry an absolute resource URL, got {res!r}")


def lint_response(url: str, status: int, headers: dict[str, str],
                  body_bytes: bytes) -> Report:
    """Run all conformance checks against one fetched (unpaid) response."""
    report = Report(url=url)

    if status == 402:
        report.add("status", PASS, "HTTP 402 Payment Required")
    else:
        report.add("status", FAIL, f"expected HTTP 402, got {status}")

    doc = _load_document(status, headers, body_bytes, report)
    if doc is None:
        return report
    if not isinstance(doc, dict):
        report.add("document", FAIL, "payment challenge is not a JSON object")
        return report

    version = report.wire_version or "2"

    v = doc.get("x402Version")
    if isinstance(v, int) and not isinstance(v, bool):
        report.add("x402Version", PASS, str(v))
    else:
        report.add("x402Version", FAIL, f"missing or non-integer: {v!r}")

    err = doc.get("error")
    if isinstance(err, str) and err.strip():
        report.add("error", PASS, f"{err!r}")
    else:
        report.add("error", WARN, "no human-readable 'error' string")

    if version == "2":
        res = doc.get("resource")
        if isinstance(res, dict) and _is_abs_url(res.get("url", "")):
            report.add("resource.url", PASS, res["url"])
        else:
            report.add("resource.url", WARN,
                       "v2 should carry a top-level resource.url (absolute)")

    accepts = doc.get("accepts")
    if not isinstance(accepts, list) or not accepts:
        report.add("accepts", FAIL, "'accepts' must be a non-empty array")
        return report
    report.add("accepts", PASS, f"{len(accepts)} payment option(s)")

    checked_host = _host(url)
    for i, entry in enumerate(accepts):
        _check_accepts_entry(i, entry, version, checked_host, report)

    ext = doc.get("extensions")
    if isinstance(ext, dict) and "bazaar" in ext:
        report.add("discovery", INFO, "advertises the 'bazaar' discovery extension")
    elif version == "1" and any(
        isinstance(e, dict) and e.get("outputSchema") for e in accepts
    ):
        report.add("discovery", INFO, "carries v1 'outputSchema' discovery hint")
    else:
        report.add("discovery", INFO,
                   "no discovery metadata (bazaar / outputSchema) — not required")

    return report


def _network_family(net: Any) -> str | None:
    if not isinstance(net, str):
        return None
    if ":" in net:
        return net.split(":", 1)[0]
    if net.startswith("base") or net in {"avalanche", "avalanche-fuji", "polygon",
                                         "polygon-amoy", "iotex", "sei", "sei-testnet"}:
        return "eip155"
    if net.startswith("solana"):
        return "solana"
    return None


def _is_abs_url(s: Any) -> bool:
    return isinstance(s, str) and (s.startswith("http://") or s.startswith("https://"))


def _host(s: Any) -> str:
    if not _is_abs_url(s):
        return ""
    rest = s.split("://", 1)[1]
    return rest.split("/", 1)[0].split("?", 1)[0].lower()
