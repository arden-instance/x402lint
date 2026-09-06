"""Tests for the optional MCP server wrapper. No network: `_fetch` / `_get_json`
are monkeypatched. Skipped entirely when the `mcp` extra isn't installed."""

import asyncio
import base64
import json

import pytest

mcp_server = pytest.importorskip("x402lint.mcp_server")

from x402lint.protocol import X402LintError  # noqa: E402


def _b64(doc):
    return base64.b64encode(json.dumps(doc).encode()).decode()


def test_tools_registered():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"lint_endpoint", "decode_payment", "check_facilitator"}


def test_decode_payment_roundtrip():
    doc = {"x402Version": 1, "accepts": [{"scheme": "exact", "network": "base"}]}
    out = mcp_server.decode_payment(_b64(doc))
    assert out["document"] == doc
    assert "x402Version=1" in out["kind"]


def test_decode_payment_rejects_garbage():
    with pytest.raises(X402LintError):
        mcp_server.decode_payment("not-base64-json!!!")


def test_lint_endpoint_uses_fetch(monkeypatch):
    challenge = {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact", "network": "base",
            "maxAmountRequired": "1000",
            "resource": "https://example.test/paid",
            "payTo": "0x0000000000000000000000000000000000000001",
            "asset": "0x0000000000000000000000000000000000000002",
            "maxTimeoutSeconds": 60,
        }],
    }
    captured = {}

    def fake_fetch(url, method, timeout, data=None):
        captured["method"] = method
        captured["data"] = data
        return 402, {"Content-Type": "application/json"}, json.dumps(challenge).encode()

    monkeypatch.setattr(mcp_server, "_fetch", fake_fetch)
    report = mcp_server.lint_endpoint("https://example.test/paid")
    assert report["url"] == "https://example.test/paid"
    assert "ok" in report and "checks" in report
    assert captured["method"] == "GET"


def test_lint_endpoint_body_switches_to_post(monkeypatch):
    def fake_fetch(url, method, timeout, data=None):
        assert method == "POST"
        assert json.loads(data) == {"q": "hi"}
        return 402, {"Content-Type": "application/json"}, b'{"x402Version": 1, "accepts": []}'

    monkeypatch.setattr(mcp_server, "_fetch", fake_fetch)
    mcp_server.lint_endpoint("https://example.test/paid", body='{"q": "hi"}')


def test_check_facilitator(monkeypatch):
    supported = {"kinds": [{"x402Version": 1, "scheme": "exact", "network": "base"}]}
    monkeypatch.setattr(mcp_server, "_get_json", lambda url, timeout: supported)
    out = mcp_server.check_facilitator("https://facilitator.test")
    assert "exact" in out["schemes"]
