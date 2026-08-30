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

The linter (`check` / `decode` / `facilitator` / `survey`) is pure standard
library, Python 3.12+. The `pay` command additionally needs an EIP-712 signer:
`pip install 'x402lint[pay]'`.

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

### `x402lint facilitator [url]`

Fetches `GET <url>/supported` and lists every `(x402Version, scheme, network)`
triple the facilitator can `verify` / `settle`, plus its advertised extensions.
Warns on unknown schemes or non-CAIP-2 v2 networks. `url` defaults to
`https://x402.org/facilitator` (the public testnet facilitator). `--json`.

```
$ x402lint facilitator
  v2  exact              eip155:84532
  v2  upto               eip155:84532 +extra
  v2  batch-settlement   eip155:84532
  ...
11 kind(s): schemes batch-settlement, exact, upto; 9 network(s); versions 1, 2
```

### `x402lint survey [catalogue]`

Pulls a discovery catalogue (`catalogue` defaults to the Coinbase CDP
`.../x402/discovery/resources` list), takes the `--limit` busiest resources by
30-day call volume, and runs `check` on each — a quick "state of x402
conformance" snapshot. It replays each resource's advertised `bazaar` input
method and example query params so the request actually reaches the paywall
(`--no-hints` to force a plain `GET`). `--json`.

```
$ x402lint survey --limit 8
ok   v2  https://x402.twit.sh/tweets/search?from=elonmusk&minLikes=100&words=bitcoin
FAIL v2  https://x402.tavily.com/search
       - accepts[1].amount: 'amount' must be a base-10 string of a positive integer, got '0.016'
...
7/8 endpoints conformant
```

Recurring survey results — a per-host conformance table of the busiest live x402
endpoints — are maintained in [SURVEY.md](./SURVEY.md), with dated snapshots in
[`data/`](./data/).

### `x402lint pay <url>`

Fetches the endpoint's 402, picks the first `exact`-scheme `accepts[]` entry
(or `--accept-index N`), and signs an EIP-3009 `TransferWithAuthorization`
payment **offline** — no transaction, no gas, just an EIP-712 signature. Prints
the `X-PAYMENT` header value a client would send back. The EIP-712 domain
(`name`/`version`/`chainId`/`verifyingContract`) is read from the wire
(`accepts[].extra` + `network` + `asset`), never hardcoded.

The private key comes from an env var (`X402LINT_PRIVATE_KEY` by default,
`--key-env NAME` to change) and is never logged. Needs the `pay` extra:

```
pip install 'x402lint[pay]'
export X402LINT_PRIVATE_KEY=0x...
$ x402lint pay https://api.example.com/data
# payer     0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A
# asset     0x036CbD53842c5426634e7929541eC2318f3dCF7e  (USDC v2, chain 84532)
# payTo     0x209693Bc6afc0C5328bA36FaF03C514EF312287C
# value     1000 atomic units
# expires   validBefore=1756431600

X-PAYMENT: eyJ4NDAyVmVyc2lvbiI6MSwic2NoZW1lIjoiZXhhY3Qi...
```

`--json` emits the payer, authorization tuple, signature, full `PaymentPayload`,
and header.

### `x402lint roundtrip <url>`

`pay`, then resend the request with the `X-PAYMENT` header and report what the
server did with it. Decodes the `X-PAYMENT-RESPONSE` header (`success`,
`transaction`, `network`); falls back to the response body's `error` string when
the payment is rejected. Exits `0` only if the payment settled, `1` otherwise.

```
export X402LINT_PRIVATE_KEY=0x...
$ x402lint roundtrip https://api.example.com/data
# payer     0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A
# payTo     0x209693Bc6afc0C5328bA36FaF03C514EF312287C
# value     1000 atomic units  (chain 84532)
# retry     HTTP 200

SETTLED  tx 0xabc123...
```

Needs the `pay` extra and a funded key for a real settlement; without funds it
reports `NOT SETTLED (insufficient_funds)` after exercising the full path.

#### `--facilitator <url>`

Settle **directly** against a facilitator's `/verify` + `/settle` rather than
re-sending to the resource server. Useful when the resource server builds its own
(CAIP-2) `paymentRequirements` and self-fails against a facilitator that only
accepts v1 friendly names there. x402lint translates the challenge into the v1
settle envelope (`base-sepolia`, `maxAmountRequired`, `x402Version: 1`) and stops
before `/settle` if `/verify` rejects the payment.

```
$ x402lint roundtrip --facilitator https://x402.org/facilitator https://x402.org/protected
# payer        0xc838ED72fd5905C30801515DdC7B5cc13F36E88D
# payTo        0x209693Bc6afc0C5328bA36FaF03C514EF312287C
# value        10000 atomic units  (base-sepolia)
# facilitator  https://x402.org/facilitator
# verify       HTTP 200  -> valid

SETTLED  tx 0x188066d0...
```

## Protocol notes

Two wire formats exist. **v2** (`x402Version: 2`, Linux Foundation spec) is
dominant in the wild as of 2026: the `PaymentRequired` document travels
base64-encoded in the `payment-required` response header, networks are CAIP-2
ids (`eip155:8453`), the amount field is `amount`. **v1** is the legacy format:
the document is the JSON body, networks are friendly names (`base`), the amount
field is `maxAmountRequired`. x402lint handles both.

## License

MIT
