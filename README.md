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
| 429 | `{"detail": str}` + `Retry-After` header | More than 10 requests per IP in 60 s, counting both endpoints together (422s count, 429s do not). |
| 503 | `{"detail": str}` | OpenAI (chat or embeddings) failed. |

`POST /api/chat/stream` takes the same body and answers with the same `404`, `422` and `429` responses, before any event is sent. Otherwise it responds `200` with `text/event-stream` and sends the answer while it is written (it never responds `503`). The page uses this endpoint. The evals call `ask()` directly.

| Event | Data | When |
|---|---|---|
| `delta` | `{"text": str}` | More answer text. Joined in order, the texts are the answer so far. |
| `done` | The `200` body of `POST /api/chat` | Last event of an answered question. Its `answer` is authoritative and may differ slightly from the joined deltas (HTML entities). |
| `error` | `{"detail": str}` | Last event when OpenAI failed, even after some deltas. The question is not answered. |

A stream that ends without `done` (an error or a client disconnect) leaves the question out of the conversation and does not extend it.

```powershell
curl.exe -N -X POST http://localhost:8000/api/chat/stream -H "Content-Type: application/json" -d '{\"question\": \"¿Cuánto cuesta un retiro inmediato?\"}'
```

How a question is answered: the chat is an agent with one tool, the help-center search. Small talk (a greeting, thanks, a goodbye or a general "what can you do", with nothing else asked) is answered without a search and with empty `sources`. Every other question is searched first, then the model decides whether to search again and with which self-contained query, and writes the answer from the documents those searches returned. Each search returns `retrieval.k` documents, and a question gets at most `retrieval.max_searches` searches (both in `backend/app.yaml`); then the model must answer with what it has. `sources` only lists documents retrieved for the current question.

Conversation memory: follow-up questions are understood from the 6 most recent exchanges of the same conversation (`conversations.max_exchanges` in `backend/app.yaml`). A conversation holds only questions and answers, never the searches or their documents. A conversation expires 15 minutes after its last answered question (`expires_in_seconds` is 900); the page warns 5 minutes before. Conversations live in the API process memory: they are lost when the page reloads or the API restarts, so **the API must run as a single process** (one worker, one replica). The answer uses the question's language. The page language follows the browser's `Accept-Language`: Spanish for `es*` (and `ca`, `gl`, `eu`), otherwise English. Models are set in `backend/app.yaml`. Allowed browser origins come from `CORS_ORIGINS`.

## Answer-quality evals (LangSmith)

```powershell
cd backend
poetry run python -m evals.run_evals
```

Runs the real agent (OpenAI, costs credits) over three LangSmith datasets, one experiment each with 3 repetitions: `support-chat-answers` (25 single questions, each in a new conversation, including compound questions that need two to four documents) and `support-chat-conversations` (9 examples: earlier turns asked live in one conversation, then the graded follow-up) and `support-chat-small-talk` (14 examples: 8 small-talk messages that must not be searched, and 6 boundary messages that must still be). Experiments are named `agentic-<chat model>[-<reasoning effort>]-k<k>-s<max_searches>`, for example `agentic-gpt-6-luna-none-k4-s3`; the baseline of the earlier fixed pipeline is `pipeline-<chat model>-k<k>` (see `openspec/changes/archive/2026-11-06-agentic-rag/design.md`). Datasets are created on the first run, and examples missing by name are added on later runs. `--dataset answers|conversations|small-talk` (repeatable) runs only some datasets and `--repetitions N` changes the repetitions; a gate only counts from a full run (all datasets, 3 repetitions). It needs an ingested index plus `OPENAI_API_KEY`, `LANGSMITH_API_KEY` and `DATABASE_URL`. Scoring:

- Code checks: expected sources, no leaked card number, `searched` (a question about Nimbo got at least one search) and `skipped_search` (a small-talk example got no search) and `search_count` (searches per question, reported as a mean).
- An LLM judge (`gpt-4.1-mini`) checks grounding, language, plain text and the per-example expectation, plus voseo on Spanish examples.

Current chat model: `gpt-6-luna` with `chat_reasoning_effort: none` on Chat Completions; with tools, OpenAI only accepts that effort level there. Measured on 2026-11-07 against `gpt-4.1-mini` on the same datasets (3 repetitions, summed):

| | sources | meets_expectation | conversations | p50 (answers) |
|---|---|---|---|---|
| `gpt-4.1-mini` | 64/76 | 70/74 | sources 25/28, meets 25/26 | 3.3 s |
| `gpt-6-luna` (`none`) | 74/75 | 74/75 | 100% | 4.5 s |

On both runs, grounded, no_forbidden_text and searched stay at 100%. The full table and diagnosis are in `openspec/changes/archive/2026-11-07-switch-chat-model-gpt-6-luna/design.md`. To go back, set `models.chat: gpt-4.1-mini` and remove `models.chat_reasoning_effort` in `backend/app.yaml`.

Small talk without a search (2026-11-09): on the small-talk dataset `skipped_search` went from 0/24 to 24/24, and a single greeting went from 3.4 s and about 4,000 tokens to 1.5 s and about 1,100 tokens (p50, first run). The results and the one accepted `grounded` miss are in `openspec/changes/small-talk-without-search/design.md`.

Results of the earlier pipeline on 2026-10-25 (`gpt-4.1-mini`, `text-embedding-3-large`, k = 8, 1 repetition):

| Metric | `support-chat-answers` | `support-chat-conversations` |
|---|---|---|
| sources | 16/16 | 8/8 |
| no_forbidden_text | 16/16 | 8/8 |
| grounded | 16/16 | 8/8 |
| correct_language | 16/16 | 8/8 |
| plain_text | 16/16 | 8/8 |
| meets_expectation | 16/16 | 8/8 |
| voseo (Spanish only) | 10/10 | 8/8 |

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
npm run test:e2e                 # builds, serves on 127.0.0.1:3100, intercepts /api/chat/stream (no backend needed)
```
