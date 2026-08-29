"""Command-line entry point for x402lint.

Subcommands:
  check <url>      fetch an endpoint unpaid, expect a 402, lint the challenge
  decode <blob>    pretty-print any base64 x402 header blob (- reads stdin)
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Sequence

from . import __version__
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

    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
