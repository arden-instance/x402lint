"""Command-line entry point for x402lint.

Subcommands:
  check <url>         fetch an endpoint unpaid, expect a 402, lint the challenge
  decode <blob>       pretty-print any base64 x402 header blob (- reads stdin)
  facilitator [url]   list the scheme/network pairs a facilitator settles
  survey [catalogue]  run `check` across the busiest discovery-catalogue endpoints
  pay <url>           sign an exact-scheme payment for an endpoint's 402 (offline)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Sequence

from . import __version__
from .catalog import (
    DEFAULT_CATALOGUE,
    DEFAULT_FACILITATOR,
    parse_catalogue,
    parse_supported,
    supported_url,
    top_resources,
)
from .protocol import X402LintError, b64json, classify, lint_response

_LEVEL_COLOR = {"PASS": "\033[32m", "WARN": "\033[33m", "FAIL": "\033[31m", "INFO": "\033[36m"}
_RESET = "\033[0m"


def _fetch(url: str, method: str, timeout: float) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, method=method, headers={
        "User-Agent": f"x402lint/{__version__}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as e:  # a 402 lands here
        return e.code, dict(e.headers.items()), e.read()
    except urllib.error.URLError as e:
        raise X402LintError(f"could not reach {url}: {e.reason}")


def _render(report, use_color: bool) -> None:
    for c in report.checks:
        if use_color:
            col = _LEVEL_COLOR.get(c.level, "")
            print(f"{col}{c.level:4}{_RESET}  {c.id}: {c.message}")
        else:
            print(f"{c.level:4}  {c.id}: {c.message}")
    n = report.counts
    print(f"\n{n['PASS']} pass, {n['WARN']} warn, {n['FAIL']} fail  "
          f"({'CONFORMANT' if not report.failed else 'NON-CONFORMANT'})")


def cmd_check(args: argparse.Namespace) -> int:
    try:
        status, headers, body = _fetch(args.url, args.method, args.timeout)
    except X402LintError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    report = lint_response(args.url, status, headers, body)
    if args.json:
        json.dump(report.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _render(report, use_color=sys.stdout.isatty() and not args.no_color)
    return 1 if report.failed else 0


def cmd_decode(args: argparse.Namespace) -> int:
    blob = sys.stdin.read() if args.blob == "-" else args.blob
    try:
        doc = b64json(blob)
    except X402LintError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.json:
        json.dump(doc, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"# {classify(doc)}\n")
        print(json.dumps(doc, indent=2))
    return 0


def _get_json(url: str, timeout: float) -> object:
    try:
        status, _headers, body = _fetch(url, "GET", timeout)
    except X402LintError as e:
        raise X402LintError(str(e))
    if status != 200:
        raise X402LintError(f"{url} returned HTTP {status}, expected 200")
    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise X402LintError(f"{url} did not return JSON: {e}")


def cmd_facilitator(args: argparse.Namespace) -> int:
    url = supported_url(args.url)
    try:
        summary = parse_supported(_get_json(url, args.timeout))
    except X402LintError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.json:
        json.dump(summary, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1 if summary["notes"] else 0

    print(f"# {url}\n")
    for k in summary["kinds"]:
        extra = " +extra" if k["extra"] else ""
        print(f"  v{k['x402Version']:<2} {str(k['scheme']):<18} {k['network']}{extra}")
    print(f"\n{len(summary['kinds'])} kind(s): "
          f"schemes {', '.join(summary['schemes']) or '-'}; "
          f"{len(summary['networks'])} network(s); "
          f"versions {', '.join(map(str, summary['versions'])) or '-'}")
    if summary["extensions"]:
        print(f"extensions: {', '.join(summary['extensions'])}")
    for note in summary["notes"]:
        print(f"WARN  {note}")
    return 1 if summary["notes"] else 0


def cmd_survey(args: argparse.Namespace) -> int:
    try:
        rows = parse_catalogue(_get_json(args.catalogue, args.timeout))
    except X402LintError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    targets = top_resources(rows, args.limit)
    if not targets:
        print("error: no usable http(s) resources in the catalogue", file=sys.stderr)
        return 2

    results = []
    for r in targets:
        target = r["resource"]
        if r.get("query") and not args.no_hints:
            target += ("&" if "?" in target else "?") + urllib.parse.urlencode(r["query"])
        method = "GET" if args.no_hints else (r.get("method") or "GET")
        entry = {"resource": target, "method": method, "calls_30d": r["calls_30d"]}
        try:
            status, headers, body = _fetch(target, method, args.timeout)
            report = lint_response(target, status, headers, body)
            entry.update(
                wire_version=report.wire_version,
                ok=not report.failed,
                counts=report.counts,
                fails=[f"{c.id}: {c.message}" for c in report.checks if c.level == "FAIL"],
            )
        except X402LintError as e:
            entry.update(wire_version=None, ok=False, error=str(e), fails=[])
        results.append(entry)

    conformant = sum(1 for e in results if e.get("ok"))
    if args.json:
        json.dump({"n": len(results), "conformant": conformant, "results": results},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    for e in results:
        mark = "ok  " if e.get("ok") else "FAIL"
        ver = f"v{e['wire_version']}" if e.get("wire_version") else "?? "
        print(f"{mark} {ver}  {e['resource']}")
        for f in e.get("fails", []):
            print(f"       - {f}")
        if e.get("error"):
            print(f"       - {e['error']}")
    print(f"\n{conformant}/{len(results)} endpoints conformant")
    return 0


def cmd_pay(args: argparse.Namespace) -> int:
    from . import pay as paymod

    key = os.environ.get(args.key_env)
    if not key:
        print(f"error: private key not found in ${args.key_env}; "
              f"export it or pass --key-env NAME", file=sys.stderr)
        return 2
    try:
        status, headers, body = _fetch(args.url, args.method, args.timeout)
        if status != 402:
            print(f"error: {args.url} returned HTTP {status}, expected 402", file=sys.stderr)
            return 2
        doc = paymod.challenge_document(status, headers, body)
        entry = paymod.select_exact_entry(doc, args.accept_index)
        out = paymod.prepare_payment(entry, key, x402_version=args.x402_version)
    except X402LintError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.json:
        json.dump({k: out[k] for k in ("payer", "authorization", "signature",
                                       "payment_payload", "header")},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    dom = out["typed_data"]["domain"]
    print(f"# payer     {out['payer']}")
    print(f"# asset     {dom['verifyingContract']}  ({dom['name']} v{dom['version']}, chain {dom['chainId']})")
    print(f"# payTo     {out['authorization']['to']}")
    print(f"# value     {out['authorization']['value']} atomic units")
    print(f"# expires   validBefore={out['authorization']['validBefore']}")
    print(f"\nX-PAYMENT: {out['header']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="x402lint", description=__doc__.splitlines()[0])
    p.add_argument("--version", action="version", version=f"x402lint {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="lint an endpoint's x402 challenge")
    c.add_argument("url")
    c.add_argument("--method", default="GET")
    c.add_argument("--timeout", type=float, default=10.0)
    c.add_argument("--json", action="store_true", help="machine-readable report")
    c.add_argument("--no-color", action="store_true")
    c.set_defaults(func=cmd_check)

    d = sub.add_parser("decode", help="pretty-print a base64 x402 blob")
    d.add_argument("blob", help="base64 string, or - for stdin")
    d.add_argument("--json", action="store_true", help="emit just the decoded JSON")
    d.set_defaults(func=cmd_decode)

    f = sub.add_parser("facilitator", help="list a facilitator's supported kinds")
    f.add_argument("url", nargs="?", default=DEFAULT_FACILITATOR,
                   help=f"facilitator base or /supported URL (default: {DEFAULT_FACILITATOR})")
    f.add_argument("--timeout", type=float, default=10.0)
    f.add_argument("--json", action="store_true", help="machine-readable summary")
    f.set_defaults(func=cmd_facilitator)

    s = sub.add_parser("survey", help="check the busiest discovery-catalogue endpoints")
    s.add_argument("catalogue", nargs="?", default=DEFAULT_CATALOGUE,
                   help=f"discovery catalogue URL (default: {DEFAULT_CATALOGUE})")
    s.add_argument("--limit", type=int, default=10, help="how many top endpoints to check")
    s.add_argument("--no-hints", action="store_true",
                   help="ignore the bazaar input method/params; plain GET each resource")
    s.add_argument("--timeout", type=float, default=10.0)
    s.add_argument("--json", action="store_true", help="machine-readable report")
    s.set_defaults(func=cmd_survey)

    y = sub.add_parser("pay", help="sign an exact-scheme payment for an endpoint's 402 (offline)")
    y.add_argument("url")
    y.add_argument("--method", default="GET")
    y.add_argument("--accept-index", type=int, default=None,
                   help="which accepts[] entry to pay (default: first 'exact')")
    y.add_argument("--key-env", default="X402LINT_PRIVATE_KEY",
                   help="env var holding the 0x private key (default: X402LINT_PRIVATE_KEY)")
    y.add_argument("--x402-version", type=int, default=1, choices=(1, 2),
                   help="x402Version to stamp on the PaymentPayload (default: 1)")
    y.add_argument("--timeout", type=float, default=10.0)
    y.add_argument("--json", action="store_true", help="machine-readable output")
    y.set_defaults(func=cmd_pay)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
