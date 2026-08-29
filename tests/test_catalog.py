"""Fixture-based tests for facilitator `/supported` and discovery-catalogue
parsing. No network — every case reads tests/fixtures/reference/."""

import json
import pathlib

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
