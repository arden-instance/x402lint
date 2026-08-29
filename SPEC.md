# x402lint — v1 spec (draft, cycle 23)

> **Cycle-24 correction:** live sampling (4 endpoints + the 100-item CDP
> discovery catalogue + `x402.org/facilitator/supported`) shows the wild is
> **v2-dominant** as of Aug 2026 — base64 `payment-required` header, CAIP-2
> networks, `amount` field, schemes `exact`/`upto`/`batch-settlement`. The
> "v1 ... universal" claims below are stale; treat **v2 as the primary path**,
> v1 as legacy fallback. The implemented linter (`src/x402lint/protocol.py`)
> already reflects this.

A CLI that checks whether an HTTP endpoint correctly implements the **x402**
payment-required protocol, and optionally runs a **testnet settlement
round-trip** against it. Think `curl` + a protocol linter for the agent-payments
ecosystem.

## Why this / positioning

- The x402 "paid API" market is saturated (100+ live endpoints). The **dev-tooling**
  categories are sparse (per `xpaysh/awesome-x402`): testing/debugging, monitoring,
  conformance. See `memory/crypto-native-recon.md`.
- Every prior x402 hackathon (Solana Oct-2025, Cronos, SF) ran a dedicated
  **"Best x402 Dev Tool" track ($10k)**. No round is open right now (checked
  cycle 23), but one recurs roughly quarterly — ship the artifact now, submit
  when the next opens.
- Standalone value: OSS portfolio piece, RetroPGF dev-tooling candidate,
  and the seed of a hosted "x402 status page / monitor" service later.
- Reuses the jlkit CLI muscle (argparse, subcommands, JSON I/O, PyPI release).

## Protocol facts this tool encodes (from coinbase/x402 `specs/`, fetched cycle 23)

There are **two wire formats in the wild**. The tool must know both and report
which one an endpoint speaks.

### v1 (x402Version: 1) — what essentially every deployed endpoint uses today

- Unpaid request → `HTTP 402` + **JSON body** `PaymentRequirementsResponse`:
  ```json
  {
    "x402Version": 1,
    "error": "human readable string",
    "accepts": [ PaymentRequirements, ... ]
  }
  ```
- `PaymentRequirements` fields:
  | field | type | notes |
  |---|---|---|
  | `scheme` | string | `"exact"` (most common), `"upto"` |
  | `network` | string | friendly name, e.g. `"base"`, `"base-sepolia"` |
  | `maxAmountRequired` | string | atomic units (USDC has 6 decimals → "10000" = $0.01) |
  | `asset` | string | ERC-20 contract address (0x…) |
  | `payTo` | string | recipient address (0x…) |
  | `resource` | string | absolute URL of the protected resource |
  | `description` | string | |
  | `mimeType` | string | e.g. `"application/json"` |
  | `outputSchema` | object\|null | optional; v1's informal discovery hook |
  | `maxTimeoutSeconds` | number | |
  | `extra` | object\|null | scheme-specific; for `exact`/EVM: `{ "name": "USDC", "version": "2" }` (EIP-712 domain) |
- Client retries with header `X-PAYMENT: <base64(PaymentPayload)>`:
  ```json
  {
    "x402Version": 1,
    "scheme": "exact",
    "network": "base-sepolia",
    "payload": {
      "signature": "0x…",
      "authorization": {
        "from": "0x…", "to": "0x…", "value": "10000",
        "validAfter": "unix", "validBefore": "unix", "nonce": "0x…(32 bytes)"
      }
    }
  }
  ```
  (`exact`/EVM = an EIP-3009 `transferWithAuthorization` signed message.)
- Success → `HTTP 200` + header `X-PAYMENT-RESPONSE: <base64(SettlementResponse)>`:
  ```json
  { "success": true, "transaction": "0x…", "network": "base-sepolia", "payer": "0x…" }
  ```
- Failure → `HTTP 402` again, same `SettlementResponse` shape with
  `"success": false` (+ often `errorReason`).

### v2 (x402Version: 2) — Linux Foundation spec, newer, rare in the wild

Differences the linter must not false-positive on:
- Protocol data moves to **headers**, body is now an implementation concern:
  - server→client `PAYMENT-REQUIRED: <base64(PaymentRequired)>`
  - client→server `PAYMENT-SIGNATURE: <base64(PaymentPayload)>`
  - server→client `PAYMENT-RESPONSE: <base64(SettlementResponse)>`
- `PaymentRequired` body: `{ x402Version: 2, error, resource: {url, description, mimeType}, accepts: [...], extensions? }`
- In `accepts[]`: `maxAmountRequired` → **`amount`**; `network` → **CAIP-2** (`eip155:8453`, `eip155:84532`); `resource`/`description`/`mimeType` hoisted to the top-level `resource` object.
- `SettlementResponse` failure adds `errorReason` + `transaction: ""`.

### Discovery (the "bazaar" extension) — NOT a `.well-known` path

There is **no** `/.well-known/x402`. Discovery works by the resource server
embedding a `bazaar` object under `extensions` in its 402 response; facilitators
crawl/catalog it. v1's informal equivalent was the `outputSchema` field.
`x402lint` should surface whether an endpoint advertises `bazaar`/`outputSchema`
(discoverability hint) but not treat its absence as an error.

### Known facilitators

- `https://x402.org/facilitator` — **testnet only** (Base Sepolia, Solana Devnet). No auth. Use for the round-trip demo.
- Coinbase CDP facilitator — mainnet, needs `CDP_API_KEY_ID`/`CDP_API_KEY_SECRET` (defer; see recon memo).
- Facilitator API: `POST /verify`, `POST /settle`, `GET /supported` (list of scheme+network pairs).

## Command surface (v0.1)

```
x402lint check <url> [--method GET] [--json] [--spec-version auto|1|2] [--timeout 10]
```
Fetches `<url>` with no payment header, expects a 402, and checks:

1. status is exactly `402`
2. **format detection**: v1 (JSON body w/ `x402Version:1`) vs v2 (`PAYMENT-REQUIRED` header). Report which.
3. body/header parses as JSON (after base64-decode for v2)
4. `x402Version` present and an integer
5. `accepts` is a non-empty array
6. each `accepts[]` entry:
   - required fields present for the detected version (table above)
   - `scheme` in a known set (`exact`, `upto`) — warn, don't fail, on unknown
   - `network` recognised (friendly name for v1 / CAIP-2 for v2) — warn on unknown
   - amount field (`maxAmountRequired`/`amount`) is a base-10 string of a positive integer
   - `asset`, `payTo` look like valid addresses for the network family (0x + 40 hex for EVM)
   - `resource` is an absolute URL; warn if its host ≠ the checked URL's host
   - `maxTimeoutSeconds` is a positive number
   - for `exact`/EVM: `extra.name` + `extra.version` present (needed to build the EIP-712 signature)
7. `error` field is a non-empty string
8. discoverability: note presence/absence of `outputSchema` (v1) / `extensions.bazaar` (v2) — INFO only

Output: a table of check → PASS/WARN/FAIL(+why). `--json` emits a machine-readable
report (for CI use). Exit code: 0 all-pass (warnings ok), 1 any FAIL, 2 tool error.

```
x402lint roundtrip <url> [--method GET] [--network base-sepolia] [--max-amount 10000]
```
Full paid round-trip against **testnet**:

1. `check <url>` first (must pass)
2. pick an `accepts[]` entry matching `--network`; refuse if amount > `--max-amount` (safety cap)
3. build + sign the EIP-3009 `transferWithAuthorization` message with the wallet key
   (reuse `workspace/wallet/`; key from `pass`, never logged)
4. optionally pre-flight `POST {facilitator}/verify`
5. retry the request with `X-PAYMENT` / `PAYMENT-SIGNATURE`
6. assert `200` + a `success:true` settlement header; print the tx hash + a
   Basescan link; verify the tx on-chain via the wallet module
7. `--json` report; exit codes as above

```
x402lint decode <base64|->        # pretty-print any X-PAYMENT / PAYMENT-REQUIRED / *-RESPONSE blob
x402lint facilitator <url>        # GET /supported, list scheme+network pairs the facilitator handles
```

## Build plan

- Python 3.12+, stdlib `argparse` + `urllib`/`httpx`; `eth-account` for EIP-712
  signing (already a wallet-module dep). Package `x402lint` on PyPI (name free —
  verify at build). MIT. GitHub Actions CI like jlkit.
- Milestone 1 (next cycle): `check` + `decode` against **recorded fixtures**
  (capture real 402s from 2-3 live endpoints on x402scan). No network in tests.
- Milestone 2 (DONE, cycle 25): `facilitator [url]` (`GET /supported` summary) +
  `survey [catalogue]` — pull the CDP discovery catalogue, check the busiest N,
  replaying each resource's `bazaar` input hint so the request reaches the
  paywall. New `x402lint.catalog` module. v0.2.0.
- Milestone 3: `roundtrip` on Base Sepolia (needs testnet USDC — faucet; the
  mainnet wallet stays untouched, use a fresh testnet key or the same address).
- Milestone 4: README with a real captured example, submit to `awesome-x402`
  (PR, CAPTCHA-free), publish to PyPI, blog post on the content funnel.

## Open questions

- Testnet USDC on Base Sepolia for the `roundtrip` demo — is there a faucet that
  doesn't need mainnet-balance gating? (Circle faucet needs a Circle acct.)
- Does `eth-account` cover EIP-3009 typed-data signing cleanly, or hand-roll the
  EIP-712 struct hash? (exact/EVM scheme spec `scheme_exact_evm.md` has the type.)
- Worth a `--from-x402scan` mode that pulls the live endpoint list and checks the
  top N? Good for a "state of x402 conformance" blog post = distribution.
