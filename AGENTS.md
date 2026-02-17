# Repo Guide (for humans + agents)

This repo will become a Telegram group bot that:

- runs via long polling (no webhooks)
- records *all* group messages to a durable history store
- builds a RAG index over that history (chunking + embeddings + retrieval)
- can answer questions and call tools (notably: web search via a local SearXNG)

## Non-negotiables

- Polling only. Don't introduce webhooks.
- Vertical-slice architecture. Prefer adding a new slice over growing shared "utils".
- Store first, process second. Ingestion must be idempotent.

## Proposed stack (can be revised)

- Language: Python 3.12+
- Telegram: `python-telegram-bot` (polling)
- HTTP: `httpx`
- Config: `pydantic-settings`
- Storage (history + metadata): Postgres (via SQLAlchemy 2.x)
- Vector store: pgvector (in Postgres)
- Embeddings: `sentence-transformers` (local) or an API embedding model (pluggable)
- LLM/tool-calling: OpenRouter via OpenAI-compatible client

## Vertical-slice layout

Keep slices independent; each owns its data access and use-cases.

Suggested layout:

- `src/tgbot/core/` shared infra only (config, logging, db session, LLM client, tool runner interfaces)
- `src/tgbot/features/ingest/` record Telegram updates/messages
- `src/tgbot/features/rag/` chunking, embedding, retrieval, answering
- `src/tgbot/features/tools/` tool registry + SearXNG search tool
- `src/tgbot/features/admin/` operational commands (status, pause logging, export)

Within a slice, prefer:

- `handlers.py` (Telegram handlers)
- `service.py` (use-cases)
- `repo.py` (DB/vector store)
- `models.py` (domain models)
- `prompts.py` (LLM prompts, if any)

## Runtime behavior expectations

- The bot should be quiet by default in groups; respond only on commands/mentions.
- To record *all* messages in a group, Telegram "privacy mode" must be disabled in BotFather.
- Always persist:
  - raw update id
  - chat id
  - message id
  - sender id
  - timestamp
  - text/caption
  - minimal metadata (reply-to, thread id, etc.)

## Tooling conventions

- This repository is public. Never commit or push private data, secrets, credentials, or personal information.
- No secrets in repo. Configure via env vars.
- Prefer small, obvious solutions over frameworks.
- Add comments only when the *why* isn't obvious.

## Environment variables (planned)

- `TELEGRAM_BOT_TOKEN`
- `DATABASE_URL` (e.g. `postgresql+psycopg://user:pass@localhost:5432/tgbot`)
- `SEARXNG_BASE_URL` (e.g. `http://localhost:8080`)
- `LLM_BASE_URL` (optional; OpenAI-compatible)
- `LLM_API_KEY` (optional)
- `LLM_MODEL` (optional)
