# Arona Cloud Gateway

Minimal OpenAI-compatible AI gateway (pure Python stdlib; also runs on Deno Deploy) for always-on, pay-per-call deployments.

## Live endpoints

| Rail | Endpoint | Price |
|---|---|---|
| Free tier | `https://fancy-stallion-9156.aronaplana-os.deno.net/v1/*` (`Authorization: Bearer arona`) | free |
| **x402** (USDC on Base) | `https://fancy-stallion-9156.aronaplana-os.deno.net/x402/v1/chat/completions` | **0.01 USDC / call** |
| **L402** (Lightning) | `https://fancy-stallion-9156.aronaplana-os.deno.net/paid/v1/chat/completions` | **2 sats / call** |
| Netlify mirror (China-direct) | `https://aronaplana.dynv6.net/gw/*` | free |

`GET /health` · `GET /v1/models` · `POST /v1/chat/completions`

Backends: Cloudflare Workers AI (REST), Pollinations, LLM7 — with automatic failover and prompt-size-aware model routing.

## Pay-per-call without an account

**x402** (agent-friendly; no signup, no KYC):

```
GET  /x402/quote                    -> 402 + PAYMENT-REQUIRED (x402 v2, Base mainnet USDC)
POST /x402/v1/chat/completions      -> Authorization header PAYMENT-SIGNATURE: <base64 payload>
```

Verified through the PayAI facilitator (no API key needed) and settled on-chain. The 402 body also carries `extensions.bazaar` discovery metadata so agents can index the service.

**L402** (Lightning):

```
GET  /paid/quote                    -> 402 + BOLT11 invoice (2 sats)
GET  /paid/check?receipt=...        -> poll -> {settled, token, quota, ttl}
POST /paid/v1/chat/completions      -> Authorization: L402 <token>
```

## OpenClaw skill

For OpenClaw agents: https://github.com/aronaplana-os/arona-gateway-skill

## Env

`ARONA_KEY` (required), `CF_AI_TOKEN` (optional), `CF_ACCOUNT_ID` (optional), `PORT` (default 8080).
