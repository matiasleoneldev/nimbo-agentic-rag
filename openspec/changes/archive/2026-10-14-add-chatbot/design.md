# Design

## Context

Greenfield: `backend/` has only a Poetry project (langchain, langchain-openai, python-dotenv) and `backend/app.yaml` (paths + display labels); `frontend/` is empty. See proposal.md for motivation and specs/ for required behavior.

Corpus facts that shape the approach (measured 2026-10-14):
- 25 PDFs under `nimbo-help-center/documents/`, 1–2 pages each, 1.4k–2.9k characters of text (~400–900 tokens).
- Fee documents (NIM-020, NIM-021, NIM-022) hold their key facts in tables; plain text extraction separates labels from values.
- `nimbo-help-center/` is git-ignored and no PDF may be committed (decision 2026-10-14), so tests generate their own PDFs.

## Goals / Non-Goals

**Goals:**
- Smallest system that satisfies the three specs, typed under `mypy --strict`, runnable on Windows.
- Every LLM/embedding call goes through one seam that tests replace with fakes.

**Non-Goals:**
- Chunking strategy for long documents, hybrid search, reranking, query rewriting / translation (revisit when evals show a need).
- Horizontal scaling (rate limiter and app state are single-process).

## Decisions

### 1. Repository layout

```
docker-compose.yml          # PostgreSQL + pgvector
backend/
  app.yaml                  # existing: paths, labels; + models, retrieval
  nimbo/                    # application package
    config.py               # loads app.yaml + env
    ingest.py               # `python -m nimbo.ingest`
    pdf_text.py             # PDF -> text with tables as rows
    chat.py                 # retrieval + answer generation
    rate_limit.py           # sliding-window limiter
    api.py                  # FastAPI app, dependencies
  tests/
    help_center_factory.py  # writes a small manifest + generated PDFs into pytest's tmp_path
  evals/run_evals.py        # LangSmith dataset + evaluation
frontend/                   # Next.js app (App Router)
```

Paths in `app.yaml` are resolved against the repository root (located from the config file's own location, never the current working directory), so commands work from any directory on Windows.

### 2. One indexed document = one chunk

Every document fits comfortably in one embedding and in the prompt, so each help-center document becomes exactly one vector-store entry. This removes splitting and the risk of cutting a table in half.
Alternative: `RecursiveCharacterTextSplitter` — rejected: no retrieval benefit at this size and it can split tables.
Ceiling: a document above ~6k tokens. The fix then is a splitter by section heading.

Embedded text = a header built from manifest metadata and the `app.yaml` labels (title, category, products, countries), followed by the extracted text. This is what `app.yaml` already says its labels are for. The header also gives cross-lingual queries more anchor terms.

### 3. PDF extraction with pdfplumber (new dependency)

`pdfplumber` exposes table detection (`find_tables` / `extract_tables`) and lets the code extract the text outside table bounding boxes. Tables are rendered one row per line, cells joined with ` | `, in reading position. Required by the "Table rows stay together" requirement.
Alternatives: `pypdf` (no table support, same label/value split as pdftotext), `unstructured` (heavy, many transitive deps), `camelot` (needs Ghostscript, painful on Windows).

### 4. Vector store: langchain-postgres `PGVectorStore` (new dependencies: `langchain-postgres`, `asyncpg`)

LangChain's maintained pgvector integration. `PGVector` is deprecated in its favor. It owns the table schema, cosine search and metadata columns, so no SQL or migrations of our own. The driver is `asyncpg` (URL scheme `postgresql+asyncpg://`). It is already a transitive dependency and becomes a declared direct one because our connection URL selects it. Alternative: psycopg async, which was rejected after the Windows check in task 3.1 (2026-10-14) failed with "Psycopg cannot use the 'ProactorEventLoop'". asyncpg works with Windows' default loop, so no event-loop workaround is needed.
Alternative: raw SQL with the `pgvector` package — more code for no added behavior.

Re-indexing (spec: re-run replaces, unreadable file leaves index untouched):
1. Read the manifest, select `documents/` entries, extract all PDFs. Any error stops here, before the DB is touched.
2. Compute all embeddings.
3. Drop and recreate the table, then insert the precomputed vectors.

Steps 1–2 hold everything in memory (25 small docs). Step 3 is not atomic, see Risks.

### 5. Retrieval and generation

- Query: embed the question (one embedding call per request; documents are never re-embedded) and take the top `k = 8` documents by cosine similarity. k was raised from 4 on 2026-10-14 after the first eval run: for "¿Cuál es el mínimo por retiro inmediato?", NIM-020 ranked 5th, 0.001 behind 4th. Each extra document adds about 700 prompt tokens. k went from 6 to 8 on 2026-10-14 after switching to `text-embedding-3-large`: the mixed question "¿Cuánto cuesta un retiro inmediato y cuál es la capital de Australia?" ranked NIM-020 7th, because two topics dilute a single query embedding. There is no similarity threshold: the model decides whether the retrieved documents answer the question. A threshold is hard to tune across languages, and the model's decision is covered by evals.
- Generation: one chat-model call. The system prompt covers every answer-content requirement of `support-chat-api`:
  - Answer only from the provided documents.
  - Write in the question's language, using voseo when that language is Spanish.
  - Use plain text, with no Markdown or HTML.
  - List the variants by country or account type when the question does not specify one.
  - Answer the covered part and name the missing part.
  - Say explicitly that the help center has no information, without inventing contact channels.
  - Say that the chat cannot see accounts.
  - Remind visitors not to share sensitive data, without echoing it.
  These are behaviors of the model, so they are verified by evals, not by deterministic tests. Documents are passed with their ids.
- Output: the model returns JSON `{"question_language": str, "answer": str, "source_ids": [str], "has_information": bool}`. `question_language` comes first so the model commits to the question's language before answering, and the user message ends with a reminder to answer in that language and not to mention document ids. Without both, answers drifted into Spanish (found in task 7.1). The JSON is parsed with a Pydantic model (`PydanticOutputParser` on plain text output, so fakes can return a JSON string). The API then:
  - drops `source_ids` not among the retrieved ids and de-duplicates them,
  - returns empty `sources` when `has_information` is false,
  - maps ids to manifest titles from the retrieved documents' metadata.
- Models live in `app.yaml` (`models.chat`, `models.embeddings`). Defaults: `text-embedding-3-large` (3072 dims) and `gpt-4.1-mini` for chat. It was chosen on 2026-10-14 because `gpt-5-mini` requires a verified OpenAI organization; switching is a one-line change in `app.yaml`. Chat models are bound to JSON mode (`response_format={"type": "json_object"}`) so the reply always parses.
- Rejected for v1: query translation/rewriting to Spanish before retrieval. It costs an extra LLM call per request. It is deferred with multi-turn query rewriting (same mechanism), and the evals include English questions to measure whether it is needed.

### 6. Fake LLM / embeddings seam

`api.py` gets the chat model and the embeddings from FastAPI dependencies (`get_chat_model`, `get_embeddings`). The ingestion entry point takes an `Embeddings` argument, and its CLI wrapper builds the OpenAI one. Tests use `app.dependency_overrides` with LangChain's own fakes (`langchain_core` `FakeListChatModel` / `GenericFakeChatModel` returning JSON strings, and `DeterministicFakeEmbedding`). A test-only subclass counts `embed_query` / `embed_documents` calls for the "embeds only the question" scenario. This is the app's composition root, not a mock of an internal module. `LANGSMITH_TRACING=false` in tests.

### 7. HTTP API (new dependencies: `fastapi`, `uvicorn`)

- Request model: Pydantic, `question: str` with `strip_whitespace`, `min_length=1`, `max_length=500`. FastAPI's default `422` covers every invalid body.
- `503`: exceptions from the model/embedding calls (`openai.APIError` and connection errors) are caught at the endpoint and returned as `{"detail": "The assistant is temporarily unavailable. Please try again later."}`. The details are logged server-side only.
- CORS: the browser calls the backend directly (`NEXT_PUBLIC_API_URL`), and the backend allows the origins listed in `CORS_ORIGINS`.
  Alternative: proxy through Next.js rewrites — rejected because the backend would then see the Next server's IP and the per-IP rate limit would collapse to one bucket.

### 8. Rate limiting (no new dependency)

An in-process sliding window: a `dict[ip, deque[timestamp]]` behind a lock, checked in an HTTP middleware on `POST /api/chat`. A dependency would miss malformed-JSON requests, which FastAPI rejects before resolving dependencies; the middleware runs before any parsing, so every `422` counts too. a `429` is not recorded, so a client hammering the endpoint cannot extend its own window. On rejection it returns `429` with `Retry-After = ceil(oldest + 60 - now)`. The clock is injectable for unit tests (the config names rate limiting as unit-test material). The client IP is `request.client.host`.
Alternative: `slowapi` — a dependency for ~25 lines, and its fixed-window default doesn't match the spec's "any 60-second window".
Ceiling: single process, and memory is never reclaimed for IPs that stop sending (deques of at most 10 entries; pruning happens on access). Behind a reverse proxy it needs trusted `X-Forwarded-For` handling, which is added when a deployment target is chosen.

### 9. Database via Docker Compose

`docker-compose.yml` runs `pgvector/pgvector:pg17` on `localhost:5432`, with an init SQL file that creates the `nimbo` and `nimbo_test` databases and `CREATE EXTENSION vector` in each. `DATABASE_URL` goes into `.env.example`. Integration tests use `TEST_DATABASE_URL` (the `nimbo_test` database) and require `docker compose up -d db`. No Docker SDK or testcontainers dependency. Everything works the same from PowerShell.

### 10. Frontend (new dependencies: `next`, `react`, `react-dom`, `tailwindcss`, `typescript`, `eslint` + `eslint-config-next`, `@playwright/test`)

The mandated stack, scaffolded with `create-next-app` (TypeScript, Tailwind, ESLint, App Router). It is a single page holding one client component. State is `useState` only: the input text, a list of `{question, answer | error, sources}` entries, and a pending flag. There is no state library or data-fetching library, since one `fetch` per question is enough. The suggested questions are a constant array in the component. Answers render as React text nodes with `whitespace-pre-line`, never `dangerouslySetInnerHTML`, which satisfies "markup is not rendered". Each suggestion is a `<button>`, keeping keyboard navigation and accessibility.

E2E (Playwright) intercepts `POST /api/chat` with `page.route` to return canned `200` / `429` / `503` responses. That mocks the backend at its HTTP boundary, the frontend's external interface, and keeps UI tests deterministic and free of OpenAI. The viewport projects are 375 px and 1440 px. Backend behavior is covered by the pytest API suite, so a full-stack E2E is deferred. The tests run against a production build (`next build` + `next start`) on `127.0.0.1:3100` with 2 workers. On Windows, `localhost` (IPv6 first), the on-demand dev server, or one worker per CPU made page loads time out. The chat input stays disabled until hydration (`useSyncExternalStore`), so keystrokes typed earlier are not lost, and tests wait for it to be enabled.

### 11. Backend dev tooling (new dev dependencies: `ruff`, `mypy`, `pytest`, `httpx`, `types-PyYAML`, `fpdf2`)

These are required by the project config. `httpx` is required by FastAPI's `TestClient`. `PyYAML` is already installed transitively (via langchain-core) and becomes a declared direct dependency because `config.py` imports it. `types-PyYAML` provides its stubs for mypy. Packages without stubs (e.g. `pdfplumber`, if needed) get `[[tool.mypy.overrides]]` entries.

`fpdf2` (dev only): no PDF may be committed, so the tests write their fixture help center (a manifest with `documents/` and `updates/` entries, and PDFs containing the NIM-020 fee table) into `tmp_path`. fpdf2 is pure Python, has no system dependencies (works on Windows), and can draw tables, which pdfplumber then has to read back.
Alternatives: `reportlab` (larger API, mixed licensing), and building PDFs by hand (fragile).
The generated table imitates the real NIM-020 layout found in the task 2.3 spike, with or without ruling lines.

### 12. Answer-quality evals (LangSmith, no new dependency)

`backend/evals/run_evals.py` creates (if missing) the LangSmith dataset `support-chat-answers` and evaluates the real chain with `langsmith.evaluate`. `langsmith` comes with langchain. The examples are the questions from the answer-quality scenarios, each with the expected source ids and language. There are two evaluators: a code evaluator (expected source ids ⊆ returned ids; empty sources for out-of-scope questions) and an LLM-as-judge evaluator built with `ChatOpenAI` (grounded? correct language? explicit "no information"? plain text?). It is run manually and costs OpenAI credits.

## Risks / Trade-offs

- [pdfplumber's default (`lines`) table strategy finds nothing if the PDF tables have no ruling lines, which would bring back the label/value split] → Task 2.3 starts with a spike on the local real NIM-020. Fallback: `table_settings` with `text` vertical/horizontal strategies. If neither keeps rows together, the extraction approach is revisited before ingestion is built.
- [psycopg's async mode (used by `PGEngine`'s background loop) is incompatible with Windows' default Proactor event loop] → Confirmed on 2026-10-14. Resolved by using the `asyncpg` driver (see decision 4).
- [Re-index step 3 is not atomic: a DB failure after the drop leaves an empty index] → Ingestion is a manual offline command; re-running it restores the index. Upgrade path: write to a new table and rename it in a transaction.
- [Cross-lingual retrieval: English questions vs Spanish documents may rank the right document lower] → Confirmed on 2026-10-14 during the end-to-end check. With `text-embedding-3-small`, "Is there a fee to receive money?" ranked NIM-020 7th, and the chat answered that it had no information. Over 8 English questions, `text-embedding-3-large` ranked the expected document 1st or 2nd every time (worst rank with small was 7th), so it is now the default. The extra cost is negligible: ~15 query tokens per question and ~$0.002 per re-index. With 25 rows there is no vector index, so the 2000-dimension HNSW limit does not apply. Query translation remains the next step if English evals regress.
- [The model sometimes answered in Spanish after detecting an English question] → Found in the same check. The user message now ends with a language reminder (9/9 correct afterwards), and the eval dataset gained English examples.
- [The model can cite the right document but misreport a table value] → The table-row extraction requirement, and the fee questions are part of the eval dataset.
- [In-memory rate limiter resets on restart and is per-process] → Acceptable for a single-instance demo; noted ceiling in decision 8.
- [Generated fixture PDFs may not behave like the real ones, so extraction tests pass on fixtures but fail on the corpus] → The generator copies the real layout found in the spike, and `test_ingest_real_corpus_indexes_25_documents` also checks the NIM-020 table row on the real corpus. That test runs locally and is skipped only when `nimbo-help-center/` is absent.
- [Prompt injection via the question] → The answer is plain text rendered as text, the model has no tools or side effects, and the system prompt restricts it to the documents. Residual risk: off-topic text, measured by evals.
