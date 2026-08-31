# Test fixtures

## `captures/`

Recorded real `402` responses from live x402 endpoints, captured **2026-08-29**
via `curl` (GET, no payment header). Each file bundles `url`, `status`,
`headers` (lower-cased), and `body`. Used by `test_protocol.py` — the suite
makes **no network calls**.

| file | endpoint | notes |
|---|---|---|
| `riddle_v2_header_only.json` | riddlex402.vercel.app | v2, challenge only in `payment-required` header, body is `{}` |
| `weather_v2_header_and_body.json` | weather.payapi.market | v2, header + a JSON body mirror; `bazaar` discovery ext |
| `onesource_v2_multi_scheme.json` | api.onesource.io | v2, two `accepts[]` options (`exact` + `batch-settlement`), `www-authenticate` too |
| `ottoai_v2_signed_offers.json` | x402.ottoai.services | v2, large header with signed offers |

All four are x402 **v2**. As of the capture date the wild is v2-dominant; no
plain v1 (`x402Version: 1` JSON-body) endpoint was found in the CDP discovery
catalogue, so the v1 path is covered by a synthetic case in `test_protocol.py`.

## `reference/`

- `cdp_discovery_resources.json` — a snapshot of the Coinbase CDP facilitator
  discovery catalogue (`GET /platform/v2/x402/discovery/resources`), 100 items.
- `facilitator_supported.json` — `GET https://x402.org/facilitator/supported`
  (testnet facilitator; scheme/network pairs it settles).
- `spec_v2_http_canonical_402.json` / `spec_v1_http_canonical_402.json` — the
  verbatim "Payment Required Signaling" example from the x402 Foundation spec's
  HTTP transport docs (`specs/transports-v{1,2}/http.md`), fetched 2026-08-31.
  `test_spec_examples.py` asserts the linter grades each with zero findings — a
  conformance checker that fails the spec's own example is miscalibrated.
