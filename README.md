# Arona Cloud Gateway

Minimal OpenAI-compatible AI gateway (pure Python stdlib) for always-on cloud deployments.

Endpoints: `GET /health`, `GET /v1/models`, `POST /v1/chat/completions`

Backends: Cloudflare Workers AI (REST), Pollinations, LLM7 — with automatic failover.

Env: `ARONA_KEY` (required), `CF_AI_TOKEN` (optional), `CF_ACCOUNT_ID` (optional), `PORT` (default 8080).
