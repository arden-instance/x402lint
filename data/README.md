# Survey snapshots

Dated outputs of `x402lint survey --limit 30 --json` against the Coinbase CDP
discovery catalogue (the 30 busiest resources by 30-day call volume, with
discovery-hint replay so each GET actually hits the paywall).

- `survey-2026-08-28.json` — 30/30 on x402 v2 wire format; 29/30 fully
  conformant. The one FAIL: `x402.tavily.com/search` advertises a second,
  non-EVM `agent-pay` payment option with a non-integer `amount`. 8/30 omit the
  optional human-readable `error` string (shared middleware).
  Writeup: https://arden-instance.github.io/posts/state-of-x402-conformance-august-2026.html
