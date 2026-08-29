# Changelog

## 0.4.0 (unreleased)

- `roundtrip <url>` — sign an `exact`-scheme payment (same path as `pay`), resend
  the request with the `X-PAYMENT` header, and report the settlement: decodes the
  `X-PAYMENT-RESPONSE` header (`success`, `transaction`, `network`), falls back to
  the response body's `error` string, and exits 0 only when the payment settled.
  `--json` for the full result. Network I/O only in the CLI layer; the signing
  path stays pure.

## 0.3.0

- `pay <url>` — fetch an endpoint's 402, pick the first `exact`-scheme
  `accepts[]` entry (or `--accept-index N`), and sign an EIP-3009
  `TransferWithAuthorization` payment **offline** (EIP-712 signature only, no
  transaction/gas). Prints the `X-PAYMENT` header value; `--json` for the full
  payload. The EIP-712 domain is read from the wire (`accepts[].extra` +
  `network` + `asset`), never hardcoded. Private key from an env var
  (`X402LINT_PRIVATE_KEY`), never logged.
- New `x402lint.pay` module (pure; the signing step is the only part needing
  `eth-account`, gated behind the `pay` optional extra).
- `python -m x402lint` now works (added `__main__`).

## 0.2.0

- `facilitator [url]` — fetch `GET /supported` and list the
  `(x402Version, scheme, network)` triples a facilitator settles; warns on
  unknown schemes / non-CAIP-2 v2 networks. Defaults to `x402.org/facilitator`.
- `survey [catalogue]` — pull a discovery catalogue (default: Coinbase CDP),
  take the busiest N resources, and run `check` on each. Uses the resource's
  advertised `bazaar` input method + example query params so the request
  actually triggers a 402 (`--no-hints` to disable). Aggregate conformance count.
- New `x402lint.catalog` module (pure parsing, fixture-tested).

## 0.1.0 (unreleased)

- `check <url>` — lint an endpoint's x402 402 challenge (v1 body + v2 header formats)
- `decode <blob>` — pretty-print / classify a base64 x402 header blob
- Fixture-based test suite (recorded real responses, no network)
