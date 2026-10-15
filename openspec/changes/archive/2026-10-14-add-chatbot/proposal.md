# Proposal

## Why

The project has no application code yet. This change delivers the first end-to-end slice of the portfolio demo: a public help-center chat for Nimbo (a fictional PayPal-like fintech) that answers visitor questions using only the Nimbo help-center documents, cites its sources, and admits when the documents do not cover a question.

## What Changes

- New ingestion command that reads `nimbo-help-center/manifest.json`, extracts text (including tables) from the PDFs under `nimbo-help-center/documents/`, embeds it once and stores it in PostgreSQL/pgvector.
- New public HTTP endpoint `POST /api/chat`: takes a plain-text question, returns an answer grounded in the retrieved documents plus the ids of the source documents. Single question → single answer; no conversation memory.
- New web page (Next.js) with a title, a subtitle, a text input, and a fixed list of suggested questions shown below the input only while the input is empty; clicking one fills the input and sends it. Responsive from phone to desktop.
- Abuse protection for a public, unauthenticated, paid-API endpoint: question length limit and per-IP rate limit.
- Project tooling the config mandates but which does not exist yet: Docker Compose for PostgreSQL/pgvector, ruff, mypy --strict, pytest, ESLint, Playwright.

### Business decisions

- 2026-10-14: The chat is public and requires no authentication.
- 2026-10-14: The chat answers only from the help-center documents; when they do not contain the answer, it MUST say so explicitly instead of guessing.
- 2026-10-14: Answers show their source document ids (e.g. `NIM-020`).
- 2026-10-14: The corpus is in Spanish; the answer is written in the language of the question (a question in English gets an English answer from Spanish documents). The UI copy is in Spanish.
- 2026-10-14: Only manifest entries under `documents/` are ingested. `updates/` (NIM-020 v2) is reserved for a later re-indexing change.
- 2026-10-14: v1 is single-turn and stateless. Multi-turn memory is deferred: first, optionally, client-sent history with query rewriting; then persistent memory (LangGraph checkpointer) together with the planned LangGraph agent.
- 2026-10-14: v1 returns the full answer in one JSON response. Streaming (SSE) is deferred to a later change that adds a separate endpoint and keeps the JSON one.
- 2026-10-14: Suggested questions are fixed (always the same four, see `support-chat-ui` spec).
- 2026-10-14: The input accepts plain text only, max 500 characters. Rate limit: 10 questions per minute per IP.
- 2026-10-14: No global spending cap in the application; the author sets a spending limit in the OpenAI platform instead.
- 2026-10-14: When an answer differs by country or account type and the question does not say which, the answer lists every applicable variant (the chat cannot ask back).
- 2026-10-14: Nimbo's Spanish voice uses voseo ("tenés", "hacé"), matching the help-center documents, in both answers and UI copy.
- 2026-10-14: The no-information answer does not point to any contact channel that the documents do not provide.
- 2026-10-14: The chat has no access to user accounts. Account-specific questions get an explicit statement of that plus the general information from the documents.
- 2026-10-14: The UI warns visitors not to share sensitive data, and the answer reminds them when a question contains it. Automatic redaction is deferred.
- 2026-10-14: The UI states that Nimbo is a fictional company and that the site is a portfolio demo.
- 2026-10-14: Questions in any language are answered in that language. Evals cover Spanish and English only.
- 2026-10-14: Partially covered questions get the covered part answered and the missing part stated explicitly.
- 2026-10-14: Sources show id and title, without links (the PDFs are not served).

## Capabilities

### New Capabilities

- `corpus-ingestion`: which help-center documents are indexed, how their text and metadata are extracted, and when embeddings are computed.
- `support-chat-api`: the `POST /api/chat` contract — input validation, grounded answers, source citations, "no information" answers, answer language, rate limiting and error responses.
- `support-chat-ui`: the public chat page — layout, suggested questions, input behavior, rendering of answers and sources, error states, responsiveness.

### Modified Capabilities

None (no specs exist yet).

## Non-goals

- Conversation memory / multi-turn context.
- Streaming responses.
- Ingesting `nimbo-help-center/updates/` or any document versioning / re-indexing.
- Authentication, user accounts, persisting chat history.
- Global spending cap (handled in the OpenAI platform).
- Automatic redaction of sensitive data in questions.
- Links to source documents.
- LangGraph agent features.

## Impact

- **Backend** (`backend/`): new FastAPI app, ingestion command, RAG chain, tests. Reads `backend/app.yaml`.
- **Frontend** (`frontend/`): new Next.js + TypeScript + Tailwind app.
- **Infrastructure**: `docker-compose.yml` with PostgreSQL + pgvector.
- **Dependencies**: new backend and frontend packages, each justified in `design.md`.
- **Config**: `backend/.env.example` gains `DATABASE_URL`.
- **External services**: OpenAI (chat + embeddings) and LangSmith (tracing) at runtime; never in automated tests.
