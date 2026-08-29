# x402lint

A conformance linter for the [x402](https://x402.org) agent-payments protocol.
Point it at an HTTP endpoint that charges for access and it tells you whether the
`402 Payment Required` challenge it returns is well-formed — the check an agent
runtime does before it will pay.

```
$ x402lint check https://riddlex402.vercel.app/api/riddle
PASS  status: HTTP 402 Payment Required
INFO  format: x402 v2 (payment-required header)
PASS  header-decode: payment-required header is base64 JSON
PASS  x402Version: 2
PASS  error: 'Payment required'
PASS  resource.url: https://riddlex402.vercel.app/api/riddle
PASS  accepts: 1 payment option(s)
PASS  accepts[0].required: all required fields present
PASS  accepts[0].scheme: 'exact'
PASS  accepts[0].network: eip155:8453 (CAIP-2)
PASS  accepts[0].amount: 2000 atomic units
PASS  accepts[0].asset: valid EVM address
PASS  accepts[0].payTo: valid EVM address
PASS  accepts[0].maxTimeoutSeconds: 300
PASS  accepts[0].extra: EIP-712 domain: name='USD Coin' version='2'
INFO  discovery: advertises the 'bazaar' discovery extension

14 pass, 0 warn, 0 fail  (CONFORMANT)
```

## Install

```
pip install x402lint
```

Pure standard library, Python 3.12+.

## Commands

### `x402lint check <url>`

Fetches `<url>` with no payment header, expects a `402`, and checks the payment
challenge:

- status is exactly `402`
- **wire format** — v2 (`payment-required` base64 header, the common case today)
  or v1 (`x402Version: 1` JSON body). Reports which.
- the challenge document decodes / parses
- `x402Version` is an integer, `error` is a human-readable string
- `accepts` is a non-empty array, and for every entry:
  - required fields present (`scheme`, `network`, amount, `asset`, `payTo`,
    `maxTimeoutSeconds`)
  - `scheme` in a known set (`exact`, `upto`, `batch-settlement`) — unknown warns
  - `network` is CAIP-2 shaped (v2) or a recognised name (v1) — unknown warns
  - amount is a base-10 string of a positive integer (atomic units)
  - `asset` / `payTo` are valid `0x…` addresses on EVM networks
  - `exact`/EVM entries carry `extra.name` + `extra.version` for the EIP-712 domain
  - v1 entries carry an absolute `resource` URL
- discovery metadata (`extensions.bazaar` / v1 `outputSchema`) — reported, not required

`--json` emits a machine-readable report (for CI). Exit code: `0` conformant
(warnings allowed), `1` any failure, `2` tool error.

### `x402lint decode <blob>`

Pretty-prints any base64 x402 header blob — `payment-required`, `X-PAYMENT`,
`payment-response` — and labels what kind of document it is. `-` reads stdin.

```
curl -sD - https://weather.payapi.market/current \
  | grep -i ^payment-required: | cut -d' ' -f2 \
  | x402lint decode -
```

## Roadmap

- `x402lint roundtrip <url>` — a full paid round-trip on Base Sepolia testnet
- `x402lint facilitator <url>` — list the scheme/network pairs a facilitator supports
- `--from-discovery` — pull a facilitator's catalogue and check the top N endpoints

## Protocol notes

Two wire formats exist. **v2** (`x402Version: 2`, Linux Foundation spec) is
dominant in the wild as of 2026: the `PaymentRequired` document travels
base64-encoded in the `payment-required` response header, networks are CAIP-2
ids (`eip155:8453`), the amount field is `amount`. **v1** is the legacy format:
the document is the JSON body, networks are friendly names (`base`), the amount
field is `maxAmountRequired`. x402lint handles both.

## License

MIT
