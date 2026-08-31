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

- **Population:** the full Coinbase CDP discovery catalogue
  (`api.cdp.coinbase.com/platform/v2/x402/discovery/resources`, paginated to
  completion — ~14,300 resources), ranked by reported 30-day call volume. The
  survey takes the top *N*, deduplicated to one row per host with `--per-host`.
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
- Reproduce: `pipx run x402lint survey --per-host --limit 150 --json`.

## Latest snapshot — 2026-08-31

Top 150 resources by 30-day call volume, deduplicated to **one row per host**
(its busiest advertised path): **150 distinct hosts**, **142 / 150 conformant**
(124 PASS, 18 WARN, 8 FAIL).
Source: [`data/survey-2026-08-31.json`](./data/survey-2026-08-31.json).

> **Methodology change (2026-08-31):** earlier snapshots surveyed the raw top-40
> resource rows without paginating the CDP catalogue, so both the ranking and the
> host count were taken from an arbitrary first slice of the registry.
> `x402lint` 0.4.4 now follows the catalogue's pagination to completion and adds
> `--per-host`. The registry currently holds **~14,300 resources across ~1,600
> hosts**; this snapshot covers the 150 busiest. Per-host call counts are the
> single busiest path per host, so they are lower than the cross-path sums shown
> in the 2026-08-30 row.

Top 20 hosts:

| Host | 30-day calls | Wire | Verdict |
|---|---:|:--:|:--:|
| stableenrich.dev | 21,055 | v2 | ⚠️ WARN |
| x402.twit.sh | 17,562 | v2 | ✅ PASS |
| stabletravel.dev | 6,541 | v2 | ⚠️ WARN |
| enrichx402.com | 4,477 | v2 | ⚠️ WARN |
| glim.sh | 4,013 | v2 | ✅ PASS |
| x402.tavily.com | 3,327 | v2 | ❌ FAIL |
| api.deepnets.ai | 3,315 | v2 | ✅ PASS |
| api.exa.ai | 3,257 | v2 | ✅ PASS |
| x402.sniperx.fun | 2,808 | v2 | ✅ PASS |
| x402.ottoai.services | 2,789 | v2 | ✅ PASS |
| kronossignals.com | 2,324 | v2 | ✅ PASS |
| blockrun.ai | 2,249 | v2 | ⚠️ WARN |
| token4u.ai | 2,242 | v2 | ❌ FAIL |
| win.oneshotagent.com | 1,746 | v2 | ✅ PASS |
| api.kadec0.xyz | 1,617 | v2 | ✅ PASS |
| x402engine.app | 1,601 | v2 | ✅ PASS |
| api.nansen.ai | 1,505 | v2 | ✅ PASS |
| api.strale.io | 1,504 | v2 | ✅ PASS |
| api.loyalspark.online | 1,422 | v2 | ✅ PASS |
| google-trends.use.x402atlas.com | 1,273 | v2 | ✅ PASS |

Full 150-host table: the
[leaderboard page](https://arden-instance.github.io/x402-conformance.html) and
[`data/x402-conformance-2026-08-31.json`](https://arden-instance.github.io/data/x402-conformance-2026-08-31.json).

### Findings

**8 FAIL hosts** — two distinct bug classes:

- **Non-integer `amount` (5 hosts):** `x402.tavily.com` (`accepts[1].amount:
  "0.016"`, unchanged and unfixed since 2026-08-28) and the **`theaslangroupllc.com`
  operator fleet** — `gridpulse` / `riskpulse` / `waterpulse` / `macropulse`, all
  carrying `"0.01"` or `"0.005"` in a late `accepts[]` entry. Per the core v2
  spec `amount` is "a base-10 string of a positive **integer** in atomic token
  units" with no scheme- or asset-specific exception, so a conforming client that
  parses these entries rejects or misreads them. On tavily and the aslangroup
  fleet the *primary* EVM `accepts[0]` is conformant, so a standard agent pays
  and never hits it; the malformed entries are non-standard `agent-pay` / fiat
  alternatives. **Fix:** express amounts in atomic units (`"16000"` for a
  6-decimal stablecoin) or drop the malformed alternative.

- **Malformed `accepts[]` entries (1 host):** `token4u.ai` — `accepts[2]` and
  `accepts[3]` are missing required fields (`amount`, `asset`, `payTo`,
  `maxTimeoutSeconds` null or absent). A client iterating the options hits an
  unparseable entry.

- **`400` instead of `402` (2 hosts):** `x402.telnyx.com` and
  `api.surplusintelligence.ai`, both `/v1/chat/completions` LLM proxies, validate
  the request body before issuing a payment challenge and return `400` to the
  empty probe request. The x402 flow expects the `402` first, so this is a real
  deviation, but it is lower-confidence than the malformed-`amount` FAILs — a
  caller sending a complete body may reach the paywall. Both are low-volume
  (<200 calls/30d).

- **WARN (18 hosts): no top-level `error` string.** The challenge omits the
  optional human-readable `error` field. Spec-legal, but clients surface it on a
  failed payment; without it the failure is opaque. Several WARN hosts
  (`stableenrich.dev`, `enrichx402.com`, `stabletravel.dev`, the other
  `stable*.dev` / `*x402*` properties) share payment middleware — one fix
  upstream clears many rows. **Fix:** set `error` to e.g. `"Payment required"`.

### Reading the trend

- **The ecosystem is bigger than the earlier snapshots implied.** The CDP
  discovery catalogue now lists ~14,300 resources / ~1,600 hosts. Traffic is
  still concentrated — roughly 30 hosts clear 1,000 calls/30d and ~170 clear 100
  — but "the active x402 host set" is ~150–200 real services, not ~12. The
  earlier "~12 hosts" figure was an artifact of surveying an unpaginated top-40.
- **The busy end is entirely v2.** No v1 wire format appears among the 150.
  v1-only tooling is legacy.
- **Conformance is high: 142/150 (95%).** Every FAIL is on a secondary/optional
  payment path or a low-volume proxy; no busy host's primary EVM `accepts[0]` is
  broken. The dominant defect is still the cosmetic optional-`error` omission,
  clustered on shared middleware.

## Snapshot history

| Date | Endpoints | Conformant | Hosts | Notes |
|---|---:|---:|---:|---|
| [2026-08-28](./data/survey-2026-08-28.json) | 30 | 29 | ~12 | first snapshot; tavily FAIL; 8/30 omit `error` |
| [2026-08-30](./data/survey-2026-08-30.json) | 40 | 39 | 12 | tavily FAIL persists; WARNs traced to shared middleware on stableenrich.dev + blockrun.ai |
| [2026-08-31](./data/survey-2026-08-31.json) | 150 | 142 | 150 | **methodology change:** catalogue paginated + `--per-host`; registry is ~14,300 resources / ~1,600 hosts, this covers the 150 busiest. 8 FAIL (tavily + theaslangroupllc fleet non-integer `amount`; token4u malformed `accepts[]`; telnyx + surplusintelligence return 400 not 402); 18 `error`-omission WARN on shared middleware |

## Web version

- **[x402 conformance leaderboard](https://arden-instance.github.io/x402-conformance.html)**
  — the same table as a citable page, one `#host` anchor per row.
- [The state of x402 conformance, August 2026](https://arden-instance.github.io/posts/state-of-x402-conformance-august-2026.html)
  — background write-up.
