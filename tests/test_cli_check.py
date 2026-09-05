"""cmd_check: --data body handling. No network (cli._fetch is monkeypatched)."""

from __future__ import annotations

import base64
import json

from x402lint import cli

_V2_HEADER = base64.b64encode(json.dumps({
    "x402Version": 2,
    "error": "Payment required",
    "accepts": [{
        "scheme": "exact",
        "network": "eip155:8453",
        "amount": "2000",
        "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "payTo": "0x209693Bc6afc0C5328bA36FaF03C514EF312287C",
        "maxTimeoutSeconds": 300,
        "extra": {"name": "USD Coin", "version": "2"},
    }],
}).encode()).decode()


def _args(**kw):
    base = dict(url="https://api.example.com/v1/chat/completions", method="GET",
                data=None, timeout=10.0, json=True, no_color=True)
    base.update(kw)
    return type("A", (), base)


def test_check_data_implies_post_and_sends_body(monkeypatch, capsys):
    seen = {}

    def fake_fetch(url, method, timeout, extra_headers=None, data=None):
        seen["method"] = method
        seen["data"] = data
        return 402, {"payment-required": _V2_HEADER}, b"{}"

    monkeypatch.setattr(cli, "_fetch", fake_fetch)
    rc = cli.cmd_check(_args(data='{"model": "gemma", "messages": []}'))
    assert rc == 0
    assert seen["method"] == "POST"
    assert json.loads(seen["data"]) == {"model": "gemma", "messages": []}


def test_check_data_invalid_json_errors(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_fetch", lambda *a, **k: (402, {}, b"{}"))
    rc = cli.cmd_check(_args(data="not json"))
    assert rc == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_check_no_data_keeps_get(monkeypatch):
    seen = {}

    def fake_fetch(url, method, timeout, extra_headers=None, data=None):
        seen["method"] = method
        seen["data"] = data
        return 402, {"payment-required": _V2_HEADER}, b"{}"

    monkeypatch.setattr(cli, "_fetch", fake_fetch)
    cli.cmd_check(_args())
    assert seen["method"] == "GET"
    assert seen["data"] is None
