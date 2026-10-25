# Nimbo Help Center chat

Portfolio demo: a public RAG chat that answers questions about **Nimbo**, a fictional PayPal-like fintech, using only its (synthetic, Spanish) help-center documents. Behavior is specified in [openspec/specs/](openspec/specs/).

## Prerequisites

- Docker Desktop (Windows: WSL2 backend)
- Python 3.14 and **Poetry 2.x** (`poetry --version`; the lock file needs Poetry 2)
- Node.js 22+
- The help-center corpus at `nimbo-help-center/` (git-ignored, not distributed)

All commands below work in PowerShell.

## Setup

```powershell
docker compose up -d db          # PostgreSQL 17 + pgvector on localhost:5432 (databases nimbo, nimbo_test)
cd backend
poetry install
copy .env.example .env           # then fill in OPENAI_API_KEY, LANGSMITH_* and check DATABASE_URL
```

## Ingestion

Builds the vector index from `nimbo-help-center/manifest.json`:

```powershell
cd backend
poetry run python -m nimbo.ingest
```

- Indexes only the manifest entries under `documents/` (`updates/` is ignored).
- Each run **replaces** the whole index (table `help_center_documents`); re-running never duplicates.
- If any selected PDF is missing or unreadable it exits with code 1 naming the file, and the existing index is left untouched.
- Document embeddings (OpenAI) are computed only here, never when answering.
- Needs `OPENAI_API_KEY` and `DATABASE_URL` (asyncpg URL, see `.env.example`).

## API

```powershell
cd backend
poetry run uvicorn nimbo.api:create_app --factory --port 8000
```

`POST /api/chat` with `{"question": "...", "conversation_id": "..."}`. `question` is 1-500 characters after trimming, plain text. `conversation_id` is optional (at most 64 characters): omit it to start a new conversation, or send the one returned by the previous answer to continue it. Public, no authentication.

| Status | Body | When |
|---|---|---|
| 200 | `{"answer": str, "sources": [{"id", "title"}], "conversation_id": str, "expires_in_seconds": int}` | Answered. `sources` is empty when the help center has no information. |
| 404 | `{"detail": str}` | `conversation_id` is unknown or expired. Nothing is answered; start a new conversation. |
| 422 | FastAPI validation error | Missing, non-string, blank or >500-character question; non-string or >64-character `conversation_id`. |
| 429 | `{"detail": str}` + `Retry-After` header | More than 10 requests per IP in 60 s (422s count, 429s do not). |
| 503 | `{"detail": str}` | OpenAI (chat or embeddings) failed. |

Conversation memory: follow-up questions are understood from the 6 most recent exchanges of the same conversation (`conversations.max_exchanges` in `backend/app.yaml`); a follow-up is first rewritten into a self-contained question, which is what gets retrieved. A conversation expires 15 minutes after its last answered question (`expires_in_seconds` is 900); the page warns 5 minutes before. Conversations live in the API process memory: they are lost when the page reloads or the API restarts, so **the API must run as a single process** (one worker, one replica). The answer uses the question's language. The page language follows the browser's `Accept-Language`: Spanish for `es*` (and `ca`, `gl`, `eu`), otherwise English. Models are set in `backend/app.yaml`. Allowed browser origins come from `CORS_ORIGINS`.

## Answer-quality evals (LangSmith)

```powershell
cd backend
poetry run python -m evals.run_evals
```

Runs the real chain (OpenAI, costs credits) over two LangSmith datasets, one experiment each: `support-chat-answers` (16 single questions, each in a new conversation) and `support-chat-conversations` (8 examples: earlier turns asked live in one conversation, then the graded follow-up). Datasets are created on the first run, and examples missing by name are added on later runs. It needs an ingested index plus `OPENAI_API_KEY`, `LANGSMITH_API_KEY` and `DATABASE_URL`. Scoring:

- Code checks: expected sources and no leaked card number.
- An LLM judge (`gpt-4.1-mini`) checks grounding, language, plain text and the per-example expectation, plus voseo on Spanish examples.

Results on 2026-10-24 (`gpt-4.1-mini`, `text-embedding-3-large`, k = 8):

| Metric | `support-chat-answers` | `support-chat-conversations` |
|---|---|---|
| sources | 15/16 | 8/8 |
| no_forbidden_text | 16/16 | 8/8 |
| grounded | 16/16 | 8/8 |
| correct_language | 16/16 | 8/8 |
| plain_text | 16/16 | 8/8 |
| meets_expectation | 16/16 | 8/8 |
| voseo (Spanish only) | 10/10 | 8/8 |

Known flaky example: `mixed-partial-question-es` returns empty `sources` about 2 times in 5. When half the question is unanswerable, the model sometimes sets `has_information=false`, which drops all sources. This happened before conversation memory too, and is still open.

How the settings got here:

- k = 4 → 6: in the first run, NIM-020 ranked 5th for "¿Cuál es el mínimo por retiro inmediato?".
- `text-embedding-3-small` → `-large` and the two English examples: the end-to-end check showed weak cross-lingual retrieval ("Is there a fee to receive money?" ranked NIM-020 7th).
- k = 6 → 8: a two-topic question diluted the query embedding.

## Backend quality gate

```powershell
cd backend
poetry run ruff format --check .
poetry run ruff check .
poetry run mypy .
poetry run pytest                # needs `docker compose up -d db`; never calls OpenAI
```

## Frontend

```powershell
cd frontend
npm install
npx playwright install chromium  # once, for the E2E tests
copy .env.example .env.local     # NEXT_PUBLIC_API_URL (default http://localhost:8000)
npm run dev                      # http://localhost:3000 (the API must allow it in CORS_ORIGINS)
```

Quality gate:

```powershell
cd frontend
npm run lint
npm run typecheck
npm run test:e2e                 # builds, serves on 127.0.0.1:3100, intercepts /api/chat (no backend needed)
```
