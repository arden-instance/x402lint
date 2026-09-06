"""An MCP server exposing x402lint's conformance checks as tools.

Run it over stdio (the default MCP transport)::

    x402lint-mcp

or::

    python -m x402lint.mcp_server

It wraps the same logic as the ``x402lint`` CLI so an agent or IDE assistant
building an x402 endpoint can lint it, decode ``X-PAYMENT`` blobs, and inspect a
facilitator without shelling out.

The ``mcp`` package is an optional dependency; install it with
``pip install "x402lint[mcp]"``.
"""

from __future__ import annotations

import json
from typing import Any

try:
    from mcp.server.mcpserver import MCPServer
except ModuleNotFoundError as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "x402lint-mcp needs the 'mcp' package: pip install \"x402lint[mcp]\""
    ) from exc

from . import __version__
from .catalog import DEFAULT_FACILITATOR, parse_supported, supported_url
from .cli import _fetch, _get_json
from .protocol import X402LintError, b64json, classify, lint_response

mcp = MCPServer(
    name="x402lint",
    version=__version__,
    instructions=(
        "Conformance checks for the x402 (HTTP 402 agent-payments) protocol. "
        "Use lint_endpoint on a URL that should answer 402, decode_payment on a "
        "base64 X-PAYMENT / accepts blob, and check_facilitator on a settlement "
        "facilitator's base URL."
    ),
)


@mcp.tool(
    description=(
        "Fetch an HTTP endpoint unpaid, expect an x402 402 challenge, and lint "
        "it against the spec. Returns {url, wire_version, ok, counts, checks[]} "
        "where each check has id/level (PASS|WARN|FAIL|INFO)/message."
    )
)
def lint_endpoint(url: str, method: str = "GET", body: str | None = None,
                  timeout: float = 15.0) -> dict[str, Any]:
    data = None
    if body is not None:
        try:
            data = json.dumps(json.loads(body)).encode()
        except json.JSONDecodeError as e:
            raise X402LintError(f"body is not valid JSON: {e}")
        if method == "GET":
            method = "POST"
    status, headers, raw = _fetch(url, method, timeout, data=data)
    return lint_response(url, status, headers, raw).to_dict()


@mcp.tool(
    description=(
        "Decode a base64 (std or url-safe) JSON blob - an X-PAYMENT header, a "
        "PaymentRequirements 'accepts' entry, or a settlement response - and "
        "classify what kind of x402 document it is."
    )
)
def decode_payment(blob: str) -> dict[str, Any]:
    doc = b64json(blob)
    return {"kind": classify(doc), "document": doc}


@mcp.tool(
    description=(
        "Fetch a facilitator's /supported endpoint and summarise which "
        "scheme/network/version combinations it settles, plus any interop "
        "warnings. Pass the facilitator base URL (defaults to x402.org)."
    )
)
def check_facilitator(url: str = DEFAULT_FACILITATOR,
                      timeout: float = 15.0) -> dict[str, Any]:
    return parse_supported(_get_json(supported_url(url), timeout))


def main() -> None:
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
