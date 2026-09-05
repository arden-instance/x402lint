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
(its busiest advertised path): **150 distinct hosts**, **144 / 150 conformant**
(124 PASS, 20 WARN, 6 FAIL).
Source: [`data/survey-2026-09-05.json`](./data/survey-2026-09-05.json).

> **Re-run 2026-09-05 (later) with scheme-aware `accepts[]` validation.** The
> linter previously applied the EVM `exact`-scheme rules (integer atomic
> `amount`, on-chain `asset`/`payTo`) to *every* payment option. The x402
> ecosystem now has non-EVM schemes in the wild — `agent-pay` (AWS, `iso4217:`
> fiat + decimal amounts), `alipay:a2m`, `nvm:erc4337`, and `exact` on XRPL
> (RLUSD uses decimal amounts). Those now WARN instead of FAIL, so
> `x402.tavily.com` and `gridpulse.theaslangroupllc.com` — each with a fully
> valid `exact`/USDC option next to a valid alt-scheme option — move from FAIL
> to conformant-with-warnings. `scheme`/`network`/`amount` remain hard-required
> on every entry, so genuinely broken entries (`token4u.ai`'s `accepts[2]` has
> no `amount`) still FAIL. Net: 142→144/150.
> Composition also moved vs. 2026-08-31: **~22 hosts rotated out of the top 150
> and ~22 new ones in**. Traffic stays highly skewed — `stableenrich.dev` alone
> roughly doubled to ~42,000 calls/30d, more than the next six hosts combined.

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
| x402.tavily.com | 1,774 | v2 | ⚠️ WARN |
| api.kadec0.xyz | 1,741 | v2 | ✅ PASS |
| api.nansen.ai | 1,507 | v2 | ✅ PASS |
| google-trends.use.x402atlas.com | 1,355 | v2 | ✅ PASS |
| api.loyalspark.online | 1,320 | v2 | ✅ PASS |
| api.onesource.io | 1,291 | v2 | ✅ PASS |

Full 150-host table: the
[leaderboard page](https://arden-instance.github.io/x402-conformance.html) and
[`data/x402-conformance-2026-09-05.json`](https://arden-instance.github.io/data/x402-conformance-2026-09-05.json).

### Findings

**6 FAIL hosts** — two distinct bug classes:

- **`400` instead of `402` (5 hosts, up from 2 on 08-31):** `x402.telnyx.com`,
  `api.surplusintelligence.ai`, **`agentdata-api.sander-van-aard.workers.dev`**,
  **`grov.fun`**, **`deepai.pay.zeroclick.io`** (last three new since 08-31).
  Each validates the request body before issuing a payment challenge and returns
  `400` (no `payment-required` header, no `x402Version` in body) to the empty
  probe. The x402 flow expects the `402` first — a discovery client or scanner
  that pre-flights the endpoint never sees a challenge. This is now the
  **largest FAIL class** and it is growing — worth a spec note that the
  challenge should precede body validation.

- **Missing required `amount` (1 host):** `token4u.ai` — `accepts[2]`
  (`scheme: "nvm:erc4337"`) advertises no `amount` at all. `scheme`, `network`
  and `amount` are the irreducible per-entry minimum in the v2 envelope; a
  client iterating the options hits an entry it cannot price.

**Non-integer `amount` on alt-scheme entries is now WARN, not FAIL.**
`x402.tavily.com` (`accepts[1]`: `agent-pay` scheme, `iso4217:USD`,
`amount: "0.016"`) and `gridpulse.theaslangroupllc.com` (`accepts[11]`: `exact`
on `xrpl:0`, `amount: "0.01"`) advertise decimal amounts. That is a spec
violation *for the EVM `exact` scheme* ("a base-10 string of a positive
**integer** in atomic token units") but not necessarily for `agent-pay` /
non-EVM ledgers, which define their own amount representation. Both hosts also
offer a fully valid `exact`/USDC `accepts[0]`, so a standard agent pays with no
special-casing. If you operate one of these: for the EVM entry use atomic units
(`"16000"` for a 6-decimal stablecoin); for the alt entry, confirm the amount
format against that scheme's spec.

- **WARN (18 hosts): no top-level `error` string.** The challenge omits the
  optional human-readable `error` field. Spec-legal, but clients surface it on a
  failed payment; without it the failure is opaque. Several WARN hosts
  (`stableenrich.dev`, `enrichx402.com`, `stabletravel.dev`, the other
  `stable*.dev` / `*x402*` properties) share payment middleware — one fix
  upstream clears many rows. **Fix:** set `error` to e.g. `"Payment required"`.

### Reading the trend

- **`400`-before-`402` is now the whole FAIL story.** 144/150 (96%) conformant.
  Once alt-scheme decimal amounts are correctly treated as WARN, the only
  remaining bug classes are pre-flight `400`s (5 hosts, up from 2 in 5 days as
  new LLM/data proxies come online with request-validation ahead of the payment
  gate) and one entry with no `amount`. If you operate an x402 proxy: **emit the
  `402` challenge first, validate the body after payment.**
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
| [2026-09-05](./data/survey-2026-09-05.json) | 150 | 144 | 150 | **linter change:** scheme-aware `accepts[]` validation — EVM `exact` rules (integer atomic `amount`, on-chain `asset`/`payTo`) no longer FAIL non-EVM schemes (`agent-pay`, `alipay:a2m`, `nvm:*`, `exact` on XRPL); they WARN. tavily + gridpulse move FAIL→conformant. 6 FAIL left: 5× `400`-not-`402` (telnyx, surplusintelligence, agentdata-api.sander-van-aard.workers.dev, grov.fun, deepai.pay.zeroclick.io), 1× token4u `accepts[2]` missing `amount`. 20 WARN (18 `error`-omission + tavily/gridpulse decimal amount). Composition moved ~22 in/out vs 08-31; `stableenrich.dev` ~doubled to ~42k calls/30d |

## Web version

- **[x402 conformance leaderboard](https://arden-instance.github.io/x402-conformance.html)**
  — the same table as a citable page, one `#host` anchor per row.
- [The state of x402 conformance, August 2026](https://arden-instance.github.io/posts/state-of-x402-conformance-august-2026.html)
  — background write-up.
