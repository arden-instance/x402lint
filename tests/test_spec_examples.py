"""Calibration tests: x402lint must pass the x402 specification's OWN canonical
`402` examples with zero findings.

Rationale (raised by peer conformance-checker authors in x402-foundation/x402
issue #3104): a conformance checker that grades the spec's own canonical example
as non-conformant is miscalibrated. These fixtures are the verbatim
"Payment Required Signaling" examples from the Foundation spec's HTTP transport
documents (v1 and v2), fetched 2026-08-31. If a future rule change makes either
example FAIL or WARN, that is a linter bug until proven otherwise.
"""

import json
import pathlib

from x402lint.protocol import FAIL, WARN, lint_response

REF = pathlib.Path(__file__).parent / "fixtures" / "reference"


def _run(fixture_name):
    fx = json.loads((REF / fixture_name).read_text())
    body = fx["body"]
    body_bytes = (body if isinstance(body, str) else json.dumps(body)).encode()
    return lint_response(fx["url"], fx["status"], fx["headers"], body_bytes)


def test_spec_v2_http_canonical_402_is_clean():
    report = _run("spec_v2_http_canonical_402.json")
    findings = [str(c) for c in report.checks if c.level in (FAIL, WARN)]
    assert not findings, findings
    assert report.wire_version == "2"
    assert not report.failed


def test_spec_v1_http_canonical_402_is_clean():
    report = _run("spec_v1_http_canonical_402.json")
    findings = [str(c) for c in report.checks if c.level in (FAIL, WARN)]
    assert not findings, findings
    assert report.wire_version == "1"
    assert not report.failed
