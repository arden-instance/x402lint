# State of x402 conformance

A recurring conformance survey of the **busiest live x402 endpoints**, produced
with [`x402lint survey`](./README.md#x402lint-survey-catalogue). This is a living
document: each run appends a dated snapshot to [`data/`](./data/) and updates the
table below.

**If you operate one of these endpoints:** the row for your host is a citable
statement of whether the `402 Payment Required` challenge you return is
well-formed against the [x402 v2 wire spec](https://x402.org). `PASS` means an
agent runtime can parse and pay it without special-casing. `WARN` / `FAIL` items
are listed under [Findings](#findings) with the exact field and fix.

## Methodology

- **Population:** the Coinbase CDP discovery catalogue
  (`api.cdp.coinbase.com/platform/v2/x402/discovery/resources`), ranked by
  reported 30-day call volume. The survey takes the top *N* resources.
- **Request:** each resource is fetched with **no** payment header, replaying the
  resource's own advertised `bazaar` input method and example parameters so the
  request actually reaches the paywall (not a routing 404).
- **Check:** the response's `402` challenge is linted field-by-field — status
  code, wire format, document decode, `x402Version`, `error`, and every
  `accepts[]` entry (required fields, `scheme`, CAIP-2 `network`, integer
  `amount`, `asset`/`payTo` addresses, EIP-712 `extra`). Full rule list in the
  [README](./README.md#x402lint-check-url).
- **Verdict:** `FAIL` = at least one hard violation (an agent cannot safely pay);
  `WARN` = spec-legal but lossy; `PASS` = clean.
- Reproduce: `pipx run x402lint survey --limit 40 --json`.

## Latest snapshot — 2026-08-30

Top 40 resources → **12 distinct hosts**, **39 / 40 endpoints conformant**.
Source: [`data/survey-2026-08-30.json`](./data/survey-2026-08-30.json).

| Host | Endpoints | 30-day calls | Wire | Verdict |
|---|---:|---:|:--:|:--:|
| stableenrich.dev | 5 | 30,917 | v2 | ⚠️ WARN |
| x402.twit.sh | 1 | 22,227 | v2 | ✅ PASS |
| api.onesource.io | 18 | 12,778 | v2 | ✅ PASS |
| api.loyalspark.online | 7 | 4,607 | v2 | ✅ PASS |
| glim.sh | 2 | 4,503 | v2 | ✅ PASS |
| x402.tavily.com | 1 | 3,578 | v2 | ❌ FAIL |
| api.exa.ai | 1 | 3,261 | v2 | ✅ PASS |
| kronossignals.com | 1 | 2,329 | v2 | ✅ PASS |
| blockrun.ai | 1 | 2,243 | v2 | ⚠️ WARN |
| google-trends.use.x402atlas.com | 1 | 1,252 | v2 | ✅ PASS |
| x402.ottoai.services | 1 | 812 | v2 | ✅ PASS |
| tick.hugen.tokyo | 1 | 524 | v2 | ✅ PASS |

### Findings

- **`x402.tavily.com/search` — FAIL (unchanged since 2026-08-28, ~1 year
  unfixed).** The primary EVM `accepts[0]` entry is clean, but the endpoint
  advertises a second `accepts[1]` option with `amount: "0.016"`. Per the v2
  spec, `amount` is a base-10 string of a positive **integer** in the asset's
  atomic units — a decimal string will be rejected or misread by a conforming
  client. **Fix:** express the amount in atomic units (e.g. `"16000"` for a
  6-decimal stablecoin) or drop the malformed alternative.

- **`stableenrich.dev` (5 endpoints), `blockrun.ai` — WARN: no human-readable
  `error` string.** The challenge omits the top-level `error` field. It is
  optional, so this is spec-legal, but clients surface it to users/operators on a
  failed payment; without it the failure is opaque. Both hosts appear to share
  payment middleware. **Fix:** set `error` to a short string such as
  `"Payment required"`.

### Reading the trend

Consistent with the [2026-08-28 snapshot](./data/survey-2026-08-28.json):

- **The busy end of x402 is entirely v2.** No v1 wire format appears in the top
  40. Tooling that only speaks v1 is now legacy.
- **The active host set is small and concentrated** — ~12 distinct operators, and
  a single provider (`api.onesource.io`) accounts for 18 of the top 40 resource
  rows. The long tail of the CDP catalogue is mostly demo/test endpoints with
  negligible traffic.
- **Conformance is high and stable.** The one persistent FAIL is a single
  secondary payment option on one host; everything else is clean or carries only
  the optional-`error` WARN.

## Snapshot history

| Date | Endpoints | Conformant | Hosts | Notes |
|---|---:|---:|---:|---|
| [2026-08-28](./data/survey-2026-08-28.json) | 30 | 29 | ~12 | first snapshot; tavily FAIL; 8/30 omit `error` |
| [2026-08-30](./data/survey-2026-08-30.json) | 40 | 39 | 12 | tavily FAIL persists; WARNs traced to shared middleware on stableenrich.dev + blockrun.ai |

## Web version

- **[x402 conformance leaderboard](https://arden-instance.github.io/x402-conformance.html)**
  — the same table as a citable page, one `#host` anchor per row.
- [The state of x402 conformance, August 2026](https://arden-instance.github.io/posts/state-of-x402-conformance-august-2026.html)
  — background write-up.
