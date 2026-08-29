"""Fixture-based tests. No network — every case is a recorded real response
under tests/fixtures/captures/ (captured 2026-08-29 from live x402 endpoints)
or a hand-built edge case."""

import base64
import json
import pathlib

import pytest

from x402lint.protocol import (
    FAIL,
    WARN,
    X402LintError,
    b64json,
    classify,
    detect_wire_version,
    lint_response,
)

CAP = pathlib.Path(__file__).parent / "fixtures" / "captures"
CAPTURES = sorted(CAP.glob("*.json"))


def load(name):
    return json.loads((CAP / name).read_text())


def run(cap):
    return lint_response(
        cap["url"], cap["status"], cap["headers"],
        cap["body"].encode() if cap.get("body") else b"",
    )


@pytest.mark.parametrize("path", CAPTURES, ids=[p.stem for p in CAPTURES])
def test_live_captures_are_conformant(path):
    """Every endpoint we captured is a real, working x402 service — it should
    pass the linter with no FAIL findings."""
    report = run(json.loads(path.read_text()))
    fails = [c for c in report.checks if c.level == FAIL]
    assert not fails, [str(c) for c in fails]
    assert report.wire_version == "2"


def test_riddle_header_only_body_is_empty_object():
    cap = load("riddle_v2_header_only.json")
    assert cap["body"] == "{}"
    report = run(cap)
    assert report.wire_version == "2"
    assert not report.failed


def test_multi_scheme_endpoint_reports_each_option():
    report = run(load("onesource_v2_multi_scheme.json"))
    accepts_line = next(c for c in report.checks if c.id == "accepts")
    assert "option" in accepts_line.message
    # batch-settlement is a known scheme, exact is too -> no scheme warnings
    assert not [c for c in report.checks if c.id.endswith(".scheme") and c.level == WARN]


# --- wire-version detection -------------------------------------------------

def test_detect_v2_by_header():
    assert detect_wire_version(402, {"Payment-Required": "eyJ..."}, None) == "2"


def test_detect_v1_by_body():
    body = {"x402Version": 1, "error": "x", "accepts": []}
    assert detect_wire_version(402, {}, body) == "1"


def test_detect_none_when_no_challenge():
    assert detect_wire_version(402, {}, {"hello": "world"}) is None


# --- synthetic edge cases -------------------------------------------------

def _v2_header(doc):
    return {"payment-required": base64.b64encode(json.dumps(doc).encode()).decode()}


GOOD_ENTRY = {
    "scheme": "exact",
    "network": "eip155:8453",
    "amount": "1000",
    "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "payTo": "0xFFc458dB291b4ABcE020fE3de4f91F2770E537b1",
    "maxTimeoutSeconds": 300,
    "extra": {"name": "USD Coin", "version": "2"},
}


def test_good_synthetic_v2_passes():
    doc = {"x402Version": 2, "error": "Payment required",
           "resource": {"url": "https://ex.com/a"}, "accepts": [GOOD_ENTRY]}
    report = lint_response("https://ex.com/a", 402, _v2_header(doc), b"")
    assert not report.failed


def test_non_402_status_fails():
    doc = {"x402Version": 2, "error": "e", "accepts": [GOOD_ENTRY]}
    report = lint_response("https://ex.com/a", 200, _v2_header(doc), b"")
    assert report.failed
    assert any(c.id == "status" and c.level == FAIL for c in report.checks)


def test_bad_amount_fails():
    bad = dict(GOOD_ENTRY, amount="0.01")
    doc = {"x402Version": 2, "error": "e", "accepts": [bad]}
    report = lint_response("https://ex.com/a", 402, _v2_header(doc), b"")
    assert any(c.id == "accepts[0].amount" and c.level == FAIL for c in report.checks)


def test_bad_evm_address_fails():
    bad = dict(GOOD_ENTRY, payTo="not-an-address")
    doc = {"x402Version": 2, "error": "e", "accepts": [bad]}
    report = lint_response("https://ex.com/a", 402, _v2_header(doc), b"")
    assert any(c.id == "accepts[0].payTo" and c.level == FAIL for c in report.checks)


def test_empty_accepts_fails():
    doc = {"x402Version": 2, "error": "e", "accepts": []}
    report = lint_response("https://ex.com/a", 402, _v2_header(doc), b"")
    assert any(c.id == "accepts" and c.level == FAIL for c in report.checks)


def test_unknown_scheme_warns_not_fails():
    weird = dict(GOOD_ENTRY, scheme="quantum")
    doc = {"x402Version": 2, "error": "e", "accepts": [weird]}
    report = lint_response("https://ex.com/a", 402, _v2_header(doc), b"")
    assert any(c.id == "accepts[0].scheme" and c.level == WARN for c in report.checks)
    assert not any(c.id == "accepts[0].scheme" and c.level == FAIL for c in report.checks)


def test_no_challenge_at_all_fails():
    report = lint_response("https://ex.com/a", 402, {}, b'{"just":"json"}')
    assert report.failed
    assert any(c.id == "format" and c.level == FAIL for c in report.checks)


def test_v1_body_format_detected_and_linted():
    doc = {
        "x402Version": 1,
        "error": "Payment required",
        "accepts": [{
            "scheme": "exact", "network": "base", "maxAmountRequired": "1000",
            "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "payTo": "0xFFc458dB291b4ABcE020fE3de4f91F2770E537b1",
            "resource": "https://ex.com/a", "maxTimeoutSeconds": 60,
            "extra": {"name": "USDC", "version": "2"},
        }],
    }
    report = lint_response("https://ex.com/a", 402, {}, json.dumps(doc).encode())
    assert report.wire_version == "1"
    assert not report.failed


# --- decode helpers -------------------------------------------------------

def test_b64json_roundtrip_unpadded():
    raw = base64.b64encode(json.dumps({"a": 1}).encode()).decode().rstrip("=")
    assert b64json(raw) == {"a": 1}


def test_b64json_rejects_garbage():
    with pytest.raises(X402LintError):
        b64json("!!!!not base64!!!!")


def test_classify_payment_required():
    doc = load_reference_first_doc()
    assert "PaymentRequired" in classify(doc)


def load_reference_first_doc():
    ref = json.loads((CAP.parent / "reference" / "cdp_discovery_resources.json").read_text())
    item = ref["items"][0]
    return {"x402Version": 2, "error": "x", "accepts": item["accepts"]}
