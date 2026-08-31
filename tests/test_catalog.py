"""Fixture-based tests for facilitator `/supported` and discovery-catalogue
parsing. No network — every case reads tests/fixtures/reference/."""

import json
import pathlib
import urllib.parse

import pytest

from x402lint.catalog import (
    parse_catalogue,
    parse_supported,
    supported_url,
    top_resources,
)
from x402lint.protocol import X402LintError

REF = pathlib.Path(__file__).parent / "fixtures" / "reference"


def load(name):
    return json.loads((REF / name).read_text())


# --- supported_url -------------------------------------------------------

@pytest.mark.parametrize("base,want", [
    ("https://x402.org/facilitator", "https://x402.org/facilitator/supported"),
    ("https://x402.org/facilitator/", "https://x402.org/facilitator/supported"),
    ("https://x402.org/facilitator/supported", "https://x402.org/facilitator/supported"),
])
def test_supported_url_normalises(base, want):
    assert supported_url(base) == want


# --- parse_supported ---------------------------------------------------

def test_parse_supported_reference():
    s = parse_supported(load("facilitator_supported.json"))
    assert s["kinds"]
    assert "exact" in s["schemes"]
    assert "batch-settlement" in s["schemes"]
    assert "eip155:84532" in s["networks"]
    assert 2 in s["versions"] and 1 in s["versions"]
    assert "builder-code" in s["extensions"]
    # the reference doc only carries known schemes and CAIP-2 networks
    assert s["notes"] == []


def test_parse_supported_flags_unknown_scheme():
    doc = {"kinds": [{"x402Version": 2, "scheme": "teleport", "network": "eip155:8453"}]}
    s = parse_supported(doc)
    assert any("teleport" in n for n in s["notes"])


def test_parse_supported_flags_non_caip2_v2_network():
    doc = {"kinds": [{"x402Version": 2, "scheme": "exact", "network": "base"}]}
    s = parse_supported(doc)
    assert any("CAIP-2" in n for n in s["notes"])


def test_parse_supported_interop_note_on_caip2_networks():
    # a real /supported (CAIP-2 networks) should carry the /verify friendly-name
    # interop note but leave `notes` (which drives exit code) clean
    s = parse_supported(load("facilitator_supported.json"))
    assert s["notes"] == []
    assert any("friendly name" in n and "eip155:84532" in n for n in s["interop"])


def test_parse_supported_no_interop_note_without_caip2():
    doc = {"kinds": [{"x402Version": 1, "scheme": "exact", "network": "base-sepolia"}]}
    s = parse_supported(doc)
    assert s["interop"] == []


def test_parse_supported_rejects_junk():
    with pytest.raises(X402LintError):
        parse_supported({"nope": 1})
    with pytest.raises(X402LintError):
        parse_supported([1, 2, 3])


# --- parse_catalogue / top_resources ---------------------------------

def test_parse_catalogue_reference():
    rows = parse_catalogue(load("cdp_discovery_resources.json"))
    assert len(rows) == 100
    r0 = rows[0]
    assert r0["resource"].startswith("https://")
    assert r0["n_accepts"] >= 1
    assert r0["networks"]
    assert isinstance(r0["calls_30d"], int)


def test_top_resources_orders_by_calls_and_caps():
    rows = parse_catalogue(load("cdp_discovery_resources.json"))
    top = top_resources(rows, 5)
    assert len(top) == 5
    calls = [r["calls_30d"] or 0 for r in top]
    assert calls == sorted(calls, reverse=True)
    assert all(r["resource"].startswith(("http://", "https://")) for r in top)


def test_parse_catalogue_extracts_bazaar_input_hint():
    rows = parse_catalogue(load("cdp_discovery_resources.json"))
    # the first reference item advertises a GET with account/network/token params
    r0 = rows[0]
    assert r0["method"] == "GET"
    assert "account" in r0["query"] and "token" in r0["query"]
    # every hint value is stringified for urlencode
    assert all(isinstance(v, str) for v in r0["query"].values())


def test_parse_catalogue_defaults_when_no_bazaar():
    rows = parse_catalogue({"items": [{"resource": "https://x/a"}]})
    assert rows[0]["method"] == "GET"
    assert rows[0]["query"] == {}


def test_top_resources_skips_unusable_urls():
    rows = [
        {"resource": None, "calls_30d": 999, "payers_30d": 1},
        {"resource": "ftp://x", "calls_30d": 999, "payers_30d": 1},
        {"resource": "https://ok.example/a", "calls_30d": 1, "payers_30d": 1},
    ]
    top = top_resources(rows, 10)
    assert [r["resource"] for r in top] == ["https://ok.example/a"]


def test_parse_catalogue_rejects_junk():
    with pytest.raises(X402LintError):
        parse_catalogue({"no_items": True})


def test_top_resources_skips_templated_paths():
    rows = [
        {"resource": "https://a.example/v1/op/:name", "calls_30d": 999, "payers_30d": 9},
        {"resource": "https://b.example/v1/{id}/x", "calls_30d": 888, "payers_30d": 8},
        {"resource": "https://c.example/v1/fx?amount=%7B%27d%27%3A1%7D",
         "calls_30d": 777, "payers_30d": 7},
        {"resource": "https://d.example/ok", "calls_30d": 1, "payers_30d": 1},
    ]
    top = top_resources(rows, 10)
    # the %7B is in the query, not the path -> d and c both survive; a and b don't
    assert "https://d.example/ok" in [r["resource"] for r in top]
    assert "https://a.example/v1/op/:name" not in [r["resource"] for r in top]
    assert "https://b.example/v1/{id}/x" not in [r["resource"] for r in top]


def test_bazaar_input_drops_non_scalar_query_values():
    item = {"resource": "https://x/a", "extensions": {"bazaar": {"info": {"input": {
        "method": "get",
        "queryParams": {"symbol": "AAPL", "opts": {"default": 1, "type": "int"}},
    }}}}}
    rows = parse_catalogue({"items": [item]})
    assert rows[0]["method"] == "GET"
    assert rows[0]["query"] == {"symbol": "AAPL"}


def test_top_resources_per_host_dedupes():
    rows = [
        {"resource": "https://a.example/x", "calls_30d": 100, "payers_30d": 1},
        {"resource": "https://a.example/y", "calls_30d": 90, "payers_30d": 1},
        {"resource": "https://b.example/z", "calls_30d": 50, "payers_30d": 1},
    ]
    top = top_resources(rows, 10, per_host=True)
    assert [r["resource"] for r in top] == ["https://a.example/x", "https://b.example/z"]


# --- _get_catalogue_doc pagination ----------------------------------

def test_get_catalogue_doc_follows_pagination(monkeypatch):
    from x402lint import cli

    pages = {
        0: {"items": [{"resource": f"https://h{i}.example/a"} for i in range(1000)],
            "pagination": {"limit": 1000, "offset": 0, "total": 1500}},
        1000: {"items": [{"resource": f"https://h{i}.example/a"} for i in range(500)],
               "pagination": {"limit": 1000, "offset": 1000, "total": 1500}},
    }

    def fake_get_json(url, timeout):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        return pages[int(q["offset"])]

    monkeypatch.setattr(cli, "_get_json", fake_get_json)
    doc = cli._get_catalogue_doc("https://cat.example/resources", 5.0)
    assert len(doc["items"]) == 1500
    assert doc["pagination"]["total"] == 1500


def test_get_catalogue_doc_unpaginated(monkeypatch):
    from x402lint import cli

    monkeypatch.setattr(
        cli, "_get_json",
        lambda url, timeout: {"items": [{"resource": "https://x/a"}]})
    doc = cli._get_catalogue_doc("https://cat.example/resources", 5.0)
    assert len(doc["items"]) == 1
