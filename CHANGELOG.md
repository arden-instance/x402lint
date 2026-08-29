# Changelog

## 0.2.0 (unreleased)

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
