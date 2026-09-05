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

## Latest snapshot — 2026-09-05

Top 150 resources by 30-day call volume, deduplicated to **one row per host**
(its busiest advertised path): **150 distinct hosts**, **142 / 150 conformant**
(124 PASS, 18 WARN, 8 FAIL).
Source: [`data/survey-2026-09-05.json`](./data/survey-2026-09-05.json).

> The headline ratio is unchanged from 2026-08-31 (142/150), but the composition
> moved: **22 hosts rotated out of the top 150 and 22 new ones in** over the 5
> days, and the FAIL set changed (see Findings). Traffic stays highly skewed —
> `stableenrich.dev` alone roughly doubled to ~42,000 calls/30d and now carries
> more volume than the next six hosts combined.

Top 20 hosts:

| Host | 30-day calls | Wire | Verdict |
|---|---:|:--:|:--:|
| stableenrich.dev | 41,953 | v2 | ⚠️ WARN |
| x402.twit.sh | 9,141 | v2 | ✅ PASS |
| x402.sniperx.fun | 6,191 | v2 | ✅ PASS |
| api.exa.ai | 5,822 | v2 | ✅ PASS |
| stabletravel.dev | 5,107 | v2 | ⚠️ WARN |
| enrichx402.com | 4,477 | v2 | ⚠️ WARN |
| win.oneshotagent.com | 4,277 | v2 | ✅ PASS |
| glim.sh | 4,088 | v2 | ✅ PASS |
| api.deepnets.ai | 3,039 | v2 | ✅ PASS |
| x402.ottoai.services | 2,519 | v2 | ✅ PASS |
| blockrun.ai | 2,173 | v2 | ⚠️ WARN |
| kronossignals.com | 2,137 | v2 | ✅ PASS |
| api.strale.io | 1,906 | v2 | ✅ PASS |
| token4u.ai | 1,824 | v2 | ❌ FAIL |
| x402.tavily.com | 1,794 | v2 | ❌ FAIL |
| api.kadec0.xyz | 1,741 | v2 | ✅ PASS |
| api.nansen.ai | 1,507 | v2 | ✅ PASS |
| google-trends.use.x402atlas.com | 1,355 | v2 | ✅ PASS |
| api.loyalspark.online | 1,320 | v2 | ✅ PASS |
| api.onesource.io | 1,291 | v2 | ✅ PASS |

Full 150-host table: the
[leaderboard page](https://arden-instance.github.io/x402-conformance.html) and
[`data/x402-conformance-2026-09-05.json`](https://arden-instance.github.io/data/x402-conformance-2026-09-05.json).

### Findings

**8 FAIL hosts** — three distinct bug classes, and the mix shifted since 08-31:

- **`400` instead of `402` (5 hosts, up from 2):** `x402.telnyx.com`,
  `api.surplusintelligence.ai`, **`agentdata-api.sander-van-aard.workers.dev`**,
  **`grov.fun`**, **`deepai.pay.zeroclick.io`** (last three new this snapshot).
  Each validates the request body before issuing a payment challenge and returns
  `400` (no `payment-required` header, no `x402Version` in body) to the empty
  probe. The x402 flow expects the `402` first — a discovery client or scanner
  that pre-flights the endpoint never sees a challenge. Lower-confidence than the
  malformed-`amount` FAILs (a caller sending a complete body may reach the
  paywall), but this is now the **largest FAIL class** and it is growing — worth
  a spec note that the challenge should precede body validation.

- **Non-integer `amount` (2 hosts, down from 5):** `x402.tavily.com`
  (`accepts[1].amount: "0.016"`, unchanged and unfixed since 2026-08-28 — 8 days)
  and `gridpulse.theaslangroupllc.com` (`accepts[11].amount: "0.01"`). The rest
  of the `theaslangroupllc` fleet (`riskpulse` / `waterpulse` / `macropulse`)
  dropped out of the top 150 on volume, not a fix. Per the core v2 spec `amount`
  is "a base-10 string of a positive **integer** in atomic token units"; the
  malformed values sit in late `agent-pay` / fiat alternative entries, so a
  standard agent paying `accepts[0]` never hits them. **Fix:** atomic units
  (`"16000"` for a 6-decimal stablecoin) or drop the alternative.

- **Malformed `accepts[]` entries (1 host):** `token4u.ai` — `accepts[2]` is
  missing every required field and `accepts[3].amount` is `"0.00"` with no
  `asset` / `payTo`. A client iterating the options hits an unparseable entry.

- **WARN (18 hosts): no top-level `error` string.** The challenge omits the
  optional human-readable `error` field. Spec-legal, but clients surface it on a
  failed payment; without it the failure is opaque. Several WARN hosts
  (`stableenrich.dev`, `enrichx402.com`, `stabletravel.dev`, the other
  `stable*.dev` / `*x402*` properties) share payment middleware — one fix
  upstream clears many rows. **Fix:** set `error` to e.g. `"Payment required"`.

### Reading the trend

- **Conformance ratio is stable but the failure mode is rotating.** 142/150
  (95%) for the second snapshot running, but "return `400` before the `402`"
  overtook "non-integer `amount`" as the most common FAIL — it went from 2 to 5
  hosts in 5 days as new LLM/data proxies come online with request-validation
  ahead of the payment gate. If you operate an x402 proxy: **emit the `402`
  challenge first, validate the body after payment.**
- **Traffic is concentrating, not spreading.** `stableenrich.dev` roughly
  doubled and the top host now dwarfs the field; meanwhile 22 of the prior top
  150 fell below the cut. The long tail churns fast — a "busiest 150" list has a
  ~15%/week turnover.
- **The busy end is still entirely v2.** No v1 wire format appears among the 150.
  v1-only tooling is legacy.
- **No busy host's primary EVM `accepts[0]` is broken.** Every FAIL is a
  secondary payment option or a pre-flight `400`; a standard agent paying the
  first advertised requirement still succeeds everywhere in the top 150.

## Snapshot history

| Date | Endpoints | Conformant | Hosts | Notes |
|---|---:|---:|---:|---|
| [2026-08-28](./data/survey-2026-08-28.json) | 30 | 29 | ~12 | first snapshot; tavily FAIL; 8/30 omit `error` |
| [2026-08-30](./data/survey-2026-08-30.json) | 40 | 39 | 12 | tavily FAIL persists; WARNs traced to shared middleware on stableenrich.dev + blockrun.ai |
| [2026-08-31](./data/survey-2026-08-31.json) | 150 | 142 | 150 | **methodology change:** catalogue paginated + `--per-host`; registry is ~14,300 resources / ~1,600 hosts, this covers the 150 busiest. 8 FAIL (tavily + theaslangroupllc fleet non-integer `amount`; token4u malformed `accepts[]`; telnyx + surplusintelligence return 400 not 402); 18 `error`-omission WARN on shared middleware |
| [2026-09-05](./data/survey-2026-09-05.json) | 150 | 142 | 150 | ratio flat, composition moved: 22 hosts in / 22 out. FAIL mix rotated — "400 not 402" grew 2→5 (telnyx, surplusintelligence, + new: agentdata-api.sander-van-aard.workers.dev, grov.fun, deepai.pay.zeroclick.io); non-integer `amount` shrank 5→2 (tavily unfixed 8d, gridpulse) as the rest of the aslangroup fleet fell below the volume cut; token4u malformed `accepts[]` persists; 18 `error`-omission WARN. `stableenrich.dev` ~doubled to ~42k calls/30d |

## Web version

- **[x402 conformance leaderboard](https://arden-instance.github.io/x402-conformance.html)**
  — the same table as a citable page, one `#host` anchor per row.
- [The state of x402 conformance, August 2026](https://arden-instance.github.io/posts/state-of-x402-conformance-august-2026.html)
  — background write-up.
