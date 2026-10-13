# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

Early scaffolding. RAG chatbot (portfolio demo) answering questions over synthetic support docs (PDFs, English) for a **fictional** PayPal-like payments company — never use real company names, branding or data.

- `backend/` — Poetry project (`package-mode = false`, venv in-project at `backend/.venv`). Only `langchain`, `langchain-openai`, `python-dotenv` installed so far; no application code yet.
- `frontend/` — empty. Planned: Next.js + TypeScript (strict) + Tailwind.
- `openspec/` — spec-driven workflow. `openspec/specs/` is empty; no changes yet.

**Read [openspec/config.yaml](openspec/config.yaml) before any design or implementation work** — it holds the binding project context (stack, testing strategy, typing rules, roadmap limits).

## Workflow: OpenSpec

`openspec/specs/` is the source of truth. Every observable behavior change (API contracts, UI, answers) MUST go through an OpenSpec change (proposal + spec deltas); undocumented user-facing behavior is a defect. Use the `/opsx:*` commands / `openspec-*` skills in `.claude/` (propose → apply → verify → archive).

Artifact rules from config: RFC 2119 keywords in specs, reuse existing spec terms (no synonyms), business decisions dated `YYYY-MM-DD` in proposals, every new dependency justified in design, every spec scenario traced to a named test (or a LangSmith eval dataset for answer quality).

## Commands

Run from `backend/`:

```
poetry install            # install deps into backend/.venv
poetry add <pkg>          # add a dependency (justify it in the OpenSpec design first)
poetry run python <file>  # run with the project venv
```

Lint/type/test tooling (ruff, `mypy --strict`, pytest) is mandated but not installed yet — add it via an OpenSpec change before relying on it.

## Fixed constraints (from openspec/config.yaml)

- Stack: Python 3.14, FastAPI, LangChain; OpenAI-only LLM/embeddings; LangSmith tracing/evals; PostgreSQL + pgvector via Docker. Don't propose alternatives without a proposal.
- Embeddings computed once at ingestion, never per query.
- Roadmap: a LangGraph support agent comes later — do not add agent/graph features or abstractions in anticipation.
- Everything (code, identifiers, comments, OpenSpec artifacts) in English.
- Must run on Windows (Docker Desktop + WSL2): no bash-only scripts or Unix-only paths.
- Secrets via env vars only; keep `backend/.env.example` in sync (currently `OPENAI_API_KEY`, `LANGSMITH_*`).
- Never read `backend/.env` (user-level config forbids it). To learn env variable names, read `backend/.env.example` instead.
- Typing: avoid `# type: ignore` / `cast(Any, ...)`; if unavoidable use a specific error code plus a reason. Missing stubs → `[[tool.mypy.overrides]]` with `ignore_missing_imports`, never relax mypy globally. TS: no `any`, `@ts-ignore`, `as unknown as X`.
- Testing: test through public interfaces (HTTP API, UI), don't mock internal modules. API integration tests run against a real Postgres/pgvector container; E2E via Playwright; unit tests only for pure non-trivial logic. Tests MUST NOT call the real OpenAI API — use fake LLM and fake embeddings.
