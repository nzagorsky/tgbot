# Telegram Group History Bot (Polling) - Project Plan

## Goal

Build a Telegram bot that sits in a group chat, records the full message history, and turns that history into a searchable RAG corpus. The bot can answer questions and call tools, including web search via a local SearXNG.

## Constraints

- Long polling only (no webhooks).
- Vertical-slice architecture (features own their handlers/use-cases/storage).
- Store raw updates/messages first; any downstream processing must be idempotent.
- Quiet-by-default in groups (respond only on commands/mentions).

## Stack

- Python 3.12+
- Package manager: `uv`
- Linting/formatting: `ruff`
- `python-telegram-bot` (polling)
- `httpx` (SearXNG + any external calls)
- `pydantic-settings` (env-driven config)
- Postgres + SQLAlchemy 2.x (durable history + job/outbox tables)
- `alembic` (database migrations)
- pgvector (vector store, in Postgres)
- Embeddings: pluggable — `sentence-transformers` (local) or API embeddings behind a common interface
- LLM: OpenRouter via OpenAI-compatible chat client (supports tool-calling)
- DSPy (offline eval + prompt/program optimization)
- Testing: `pytest` with fixtures (test-container or test DB)

## Slice map (vertical slices)

- `features/ingest`: Telegram update handlers that persist messages/updates (idempotent)
- `features/rag`: chunking, embedding, vector indexing, retrieval, answer composition
- `features/tools`: tool registry + SearXNG search tool + tool-call execution
- `features/admin`: operational commands (status, pause logging, export)
- `core`: config/logging/db session + small interfaces shared by slices

## Data model (high level)

- `telegram_updates`: update_id, chat_id, raw payload hash, received_at
- `messages`: (chat_id, message_id) unique, sender_id, sent_at, text/caption, reply_to, thread_id, metadata jsonb
- `message_events`: edits/new messages as append-only events (optional but useful)
- `chunks`: chunk_id, chat_id, source message range/ids, text, embedding vector, created_at
- `jobs/outbox`: queue of "needs chunking/embedding" work items for incremental processing

## Stages (incremental delivery)

### Stage 0 - Repo bootstrap

- `uv` project with `pyproject.toml`, dev dependencies (`ruff`, `pytest`)
- `src/tgbot/` package skeleton matching the slice layout in AGENTS.md
- `pydantic-settings` config loading from env vars
- Docker Compose for Postgres+pgvector and SearXNG
- Alembic setup (initial empty migration)
- `run` entry point that starts the bot in polling mode
- CI-ready: `ruff check`, `pytest` pass on empty project

Acceptance:
- `uv run python -m tgbot` starts the bot, connects via polling with `TELEGRAM_BOT_TOKEN`.
- `alembic upgrade head` runs cleanly against the Docker Compose Postgres.
- `ruff check` and `pytest` pass.

### Stage 1 - Message ingestion (store first)

- Alembic migration for `telegram_updates` and `messages` tables
- Persist every message/update the bot sees (text + key metadata)
- Idempotency (dedupe by update_id and/or (chat_id, message_id))
- Quiet-by-default: no chatter unless `/status` or `/help`
- Tests: repo-layer tests with a real Postgres fixture

Acceptance:
- Adding the bot to a group results in durable message history in Postgres.
- Duplicate updates are silently ignored.

### Stage 2 - Chunking + indexing pipeline

- Define chunk format (speaker/time-stamped transcript blocks)
- Chunking strategy: time-gap + max-size (see "Chunking strategy" section below)
- Create chunk records from stored messages; store embedding vectors in the `chunks` table (pgvector)
- Backfill CLI command to chunk + embed existing history
- Incremental path: new messages trigger chunking via the jobs/outbox table
- Tests: chunker unit tests with synthetic message sequences

Acceptance:
- Given a chat's stored history, the backfill command builds a vector index.
- New messages are incrementally chunked and indexed.
- `SELECT` with pgvector nearest-neighbor retrieves relevant chunks for a query.

### Stage 2 — Chunking strategy (TBD)

> This section is a working design doc. Lock it in before implementing Stage 2.

**Problem:** Group chat traffic is bursty — sometimes 50 messages in 5 minutes,
sometimes 1 message per hour. Fixed-size windows cut across conversations;
pure time windows produce wildly inconsistent chunk sizes.

**Approach: time-gap + max-size (v1)**

Scan messages in chronological order per chat. Accumulate into a chunk until one
of these boundaries fires:
1. **Time gap** — silence of ≥ T minutes between consecutive messages starts a
   new chunk. (T is tunable; starting guess: 15 min.)
2. **Max size** — chunk exceeds M messages or K tokens, whichever comes first.
   Split at that point. (Starting guess: M=80 messages, K=1500 tokens.)
3. **Min size** — if a chunk would be < N messages, merge it forward into the
   next chunk instead of emitting it standalone. (Starting guess: N=3.)

Each chunk is formatted as a transcript:

```
[2025-02-17 14:02] alice: Has anyone tried the new API?
[2025-02-17 14:03] bob: Yeah, it's broken on auth
[2025-02-17 14:05] alice: Same here — getting 401s
```

Chunk metadata: chat_id, first/last message id, time range, participant list,
message count.

**Future improvements (not v1):**
- Reply-chain awareness: group messages sharing a reply_to chain into the same
  chunk even if interleaved with other messages.
- Semantic boundary detection: use embedding similarity between consecutive
  messages to detect topic shifts within a time window.
- Overlapping chunks: emit chunks with a sliding window overlap so boundary
  messages appear in two chunks, improving retrieval recall.

**Open tuning questions:**
- Best values for T / M / K / N — will need empirical tuning once real data
  flows through.
- Whether to store raw transcript or a cleaned/summarized version in the chunk
  text field.

### Stage 3 - RAG answering (no tools yet)

- `/ask <question>` command (stateless — no multi-turn context in v1)
- Retrieve relevant chunks via pgvector nearest-neighbor search
- Compose an answer with citations (Telegram message links where possible, else timestamps)
- Guardrails: refuse if no relevant context; avoid hallucinating citations
- Prompts live in `features/rag/prompts.py`

Acceptance:
- Bot answers group questions with quoted/cited context from the chat history.

### Stage 4 - Evals + DSPy optimization

- Add an eval harness for retrieval + grounded answering
- Build a small labeled eval set from real chat history (questions, gold message ids/citations, expected abstain where applicable)
- Track core metrics: Recall@k (retrieval), citation precision/recall (grounding), abstention quality, latency
- Use DSPy to optimize retrieval/answer prompts against the eval set; keep compiled config/versioned artifacts
- Add a lightweight regression run (small subset) to catch quality regressions early

Acceptance:
- Eval metrics meet initial thresholds and are reproducible across runs.

### Stage 5 - Tool calling + SearXNG search

- Implement a `searxng_search` tool (query, timeouts, safe defaults)
- Tool-call loop in LLM client (bounded steps, logging)
- `/search <query>` direct command as a deterministic fallback
- Tool registry is extensible: new tools implement a `Tool` protocol and self-register

Acceptance:
- Bot can decide to search the web, then incorporate results into answers.

### Stage 6 - Ops + admin

- `/status`, `/pause_logging`, `/resume_logging`, `/export_chat`
- Retention controls (per-chat opt-out/pause; optional redaction)
- Observability: structured logs; basic metrics hooks

Acceptance:
- Bot is operable in real groups without spamming and with clear admin controls.
