# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

RAG chatbot (portfolio demo) answering questions over synthetic support docs (Spanish PDFs) for **Nimbo**, a fictional PayPal-like payments company. Never use real company names, branding or data. [README.md](README.md) has setup and every command.

- `backend/` — Poetry 2 project (`package-mode = false`, venv at `backend/.venv`). Package `nimbo/`:
  - `config.py`: `app.yaml` + env.
  - `pdf_text.py`: pdfplumber, tables as `a | b` rows.
  - `ingest.py`: `python -m nimbo.ingest`.
  - `chat.py`: LangGraph agent loop with a help-center search tool, `ask()`.
  - `conversations.py`: open conversations and their expiry.
  - `rate_limit.py`
  - `api.py`: `uvicorn nimbo.api:create_app --factory`.

  Also `tests/` (pytest; generated fixture PDFs, fakes in `tests/fakes.py`) and `evals/run_evals.py` (LangSmith).
- `frontend/` — Next.js 16 app, single page `app/page.tsx`; Playwright E2E in `e2e/`.
- `docker-compose.yml` — `db` service, `pgvector/pgvector:pg17`, databases `nimbo` and `nimbo_test`.
- `nimbo-help-center/` — the corpus. It is git-ignored and no PDF may be committed.
- `openspec/` — spec-driven workflow; first change: `add-chatbot`.

**Read [openspec/config.yaml](openspec/config.yaml) before any design or implementation work** — it holds the binding project context (stack, testing strategy, typing rules, roadmap limits).

## Workflow: OpenSpec

`openspec/specs/` is the source of truth. Every observable behavior change (API contracts, UI, answers) MUST go through an OpenSpec change (proposal + spec deltas); undocumented user-facing behavior is a defect. Use the `/opsx:*` commands / `openspec-*` skills in `.claude/` (propose → apply → verify → archive).

Artifact rules from config: RFC 2119 keywords in specs, reuse existing spec terms (no synonyms), business decisions dated `YYYY-MM-DD` in proposals, every new dependency justified in design, every spec scenario traced to a named test (or a LangSmith eval dataset for answer quality).

## Commands

Poetry 2 is required; on this machine `poetry` is 1.8, so use `poetry-2.2.1`.

```
docker compose up -d db                 # repo root; needed by pytest and the app
# backend/
poetry install
poetry run ruff format . ; poetry run ruff check . ; poetry run mypy . ; poetry run pytest
poetry run python -m nimbo.ingest       # rebuild the index (real OpenAI embeddings)
poetry run uvicorn nimbo.api:create_app --factory --port 8000
poetry run python -m evals.run_evals    # LangSmith evals, real OpenAI (costs credits)
# frontend/
npm run dev ; npm run lint ; npm run typecheck ; npm run test:e2e
```

Gotchas:
- Use the `postgresql+asyncpg://` driver. Async psycopg fails on Windows' Proactor event loop.
- `PGEngine.close()` is async-only, so engines live for the whole process.
- Playwright runs on `127.0.0.1:3100` with 2 workers. `localhost` (IPv6 first) and more workers make page loads time out on Windows.

## Fixed constraints (from openspec/config.yaml)

- Stack: Python 3.14, FastAPI, LangChain; OpenAI-only LLM/embeddings; LangSmith tracing/evals; PostgreSQL + pgvector via Docker. Don't propose alternatives without a proposal.
- Embeddings computed once at ingestion, never per query.
- Roadmap: since 2026-11-06 (change `agentic-rag`) the chat is a LangGraph agent whose only tool is the help-center search. Every new tool or support-agent capability needs its own proposal; no abstractions in anticipation.
- Everything (code, identifiers, comments, OpenSpec artifacts) in English.
- Must run on Windows (Docker Desktop + WSL2): no bash-only scripts or Unix-only paths.
- Secrets via env vars only; keep `backend/.env.example` (`OPENAI_API_KEY`, `LANGSMITH_*`, `DATABASE_URL`, `TEST_DATABASE_URL`, `CORS_ORIGINS`) and `frontend/.env.example` (`NEXT_PUBLIC_API_URL`) in sync.
- Never read `backend/.env` (user-level config forbids it). To learn env variable names, read `backend/.env.example` instead.
- Typing: avoid `# type: ignore` / `cast(Any, ...)`; if unavoidable use a specific error code plus a reason. Missing stubs → `[[tool.mypy.overrides]]` with `ignore_missing_imports`, never relax mypy globally. TS: no `any`, `@ts-ignore`, `as unknown as X`.
- Testing: test through public interfaces (HTTP API, UI), don't mock internal modules. API integration tests run against a real Postgres/pgvector container; E2E via Playwright; unit tests only for pure non-trivial logic. Tests MUST NOT call the real OpenAI API — use fake LLM and fake embeddings.
