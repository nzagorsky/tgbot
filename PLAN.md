# Telegram Group History Bot (Polling) - Project Plan

## Goal

Build a Telegram bot that sits in a group chat, records the full message history, and turns that history into a searchable RAG corpus. The bot can answer questions and call tools, including web search via a local SearXNG.

## Constraints

- Long polling only (no webhooks).
- Vertical-slice architecture (features own their handlers/use-cases/storage).
- Store raw updates/messages first; any downstream processing must be idempotent.
- Quiet-by-default in groups (respond only on commands/mentions).

## Suggested baseline stack (v1)

- Python 3.14+
- `python-telegram-bot` (polling)
- `httpx` (SearXNG + any external calls)
- `pydantic-settings` (env-driven config)
- Postgres + SQLAlchemy 2.x (durable history + job/outbox tables)
- pgvector (vector store in Postgres)
- Embeddings: `sentence-transformers` (local) behind an interface
- LLM: OpenRouter via OpenAI-compatible chat client (supports tool-calling)
- DSPy (offline eval + prompt/program optimization)

## Slice map (vertical slices)

- `features/ingest`: Telegram update handlers that persist messages/updates (idempotent)
- `features/rag`: chunking, embedding, vector indexing, retrieval, answer composition
- `features/tools`: tool registry + SearXNG search tool + tool-call execution
- `features/admin`: operational commands (status, pause logging, export)
- `core`: config/logging/db session + small interfaces shared by slices

## Data model (high level)

- `telegram_updates`: update_id, chat_id, raw payload hash, received_at
- `messages`: (chat_id, message_id) unique, sender_id, sent_at, text/caption, reply_to, thread_id, metadata
- `message_events`: edits/new messages as append-only events (optional but useful)
- `chunks`: chunk_id, chat_id, source message range/ids, text, created_at
- `embeddings`: chunk_id, vector id, model id, created_at
- `jobs/outbox`: queue of "needs chunking/embedding" work items for incremental processing

## Stages (incremental delivery)

### Stage 0 - Repo bootstrap

- Minimal project skeleton + config system
- Docker compose for local dependencies (Postgres+pgvector; SearXNG is external but document it)
- `run` command that starts the bot in polling mode

Acceptance:
- Bot starts with `TELEGRAM_BOT_TOKEN` and connects via polling.

### Stage 1 - Message ingestion (store first)

- Persist every message/update the bot sees (text + key metadata)
- Idempotency (dedupe by update_id and/or (chat_id, message_id))
- Quiet-by-default

### Stage 2 - Chunking + indexing pipeline (offline-first)

- Define chunk format (speaker/time-stamped transcript blocks)
- Create chunk records from stored messages
- Add embeddings + vector store indexing
- Backfill command/script to index existing history; incremental job path for new messages

Acceptance:
- Given a chat's stored history, the bot can build a vector index and retrieve top-k chunks.

### Stage 3 - RAG answering (no tools yet)

- `/ask <question>` command
- Retrieve relevant chunks, compose an answer with citations (message ids + timestamps)
- Guardrails: refuse if no relevant context; avoid hallucinating citations

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

Acceptance:
- Bot can decide to search the web, then incorporate results into answers.

### Stage 6 - Ops + admin

- `/status`, `/pause_logging`, `/resume_logging`, `/export_chat`
- Retention controls (per-chat opt-out/pause; optional redaction)
- Observability: structured logs; basic metrics hooks

Acceptance:
- Bot is operable in real groups without spamming and with clear admin controls.
