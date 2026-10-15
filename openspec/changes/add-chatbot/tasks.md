# Tasks

## 1. Infrastructure and tooling

- [x] 1.1 Add `docker-compose.yml` (service `db`, image `pgvector/pgvector:pg17`, port 5432) plus an init SQL script that creates databases `nimbo` and `nimbo_test` with `CREATE EXTENSION vector`. Verify that `docker compose up -d db` starts it and that `\dx` in both databases lists `vector`.
- [x] 1.2 Add backend dependencies (`fastapi`, `uvicorn`, `pdfplumber`, `langchain-postgres`, `asyncpg`, `pyyaml`) and dev dependencies (`ruff`, `mypy`, `pytest`, `httpx`, `types-PyYAML`, `fpdf2`) with `poetry add`. Verify that `poetry install` succeeds.
- [x] 1.3 Configure ruff, `mypy --strict` (overrides only for stub-less packages) and pytest in `backend/pyproject.toml`; create the empty `nimbo/` package and `tests/`. Verify that `poetry run ruff check .`, `poetry run mypy .` and `poetry run pytest` exit 0.
- [x] 1.4 Add `DATABASE_URL`, `TEST_DATABASE_URL` and `CORS_ORIGINS` to `backend/.env.example`. Update CLAUDE.md (Project state + Commands: compose, lint, type-check, test). Verify that every documented command runs as written in PowerShell.

## 2. Configuration and PDF text extraction

- [x] 2.1 Implement `nimbo/config.py`: load `app.yaml` (paths resolved against the repo root derived from the file location; add `models` and `retrieval.k` keys) and env vars. Verify with `test_config_resolves_paths_from_any_cwd`.
- [x] 2.2 Implement `tests/help_center_factory.py` (pytest fixture): use fpdf2 to write into `tmp_path` a manifest with `documents/NIM-004`, `documents/NIM-020` and `updates/NIM-020` entries plus generated PDFs. The NIM-020 PDF reproduces the real fee table layout found in the 2.3 spike. No PDF is written inside the repository. Verify with `git status` (no new PDFs) and through the 3.x tests.
- [x] 2.3 Spike first: run pdfplumber table detection on the local real `nimbo-help-center/documents/NIM-020` (not committed) (default strategy, then `text` strategies) and confirm that the fee rows come out with label and value together; stop and revisit the design if they don't. Then implement `nimbo/pdf_text.py` with pdfplumber: text outside tables plus table rows rendered as one line each (cells joined with ` | `). Verify with `test_pdf_text_keeps_table_rows_together` (scenario "Fee table row is preserved", using the generated NIM-020).

## 3. Corpus ingestion

- [x] 3.1 First confirm that `PGVectorStore` connects and runs a similarity search on Windows (apply the selector-event-loop fallback from design Risks if needed). Then implement `nimbo/ingest.py` (`python -m nimbo.ingest`): select `documents/` entries, extract all texts first, build the metadata header from the `app.yaml` labels, embed all, then drop/recreate the `PGVectorStore` table and insert. Take an `Embeddings` argument; the CLI builds OpenAI embeddings. Verify against `nimbo_test` with `DeterministicFakeEmbedding` using these tests:
  - `test_ingest_indexes_only_documents_folder` (scenario "Only documents/ entries are indexed")
  - `test_ingest_stores_manifest_metadata` (scenario "Metadata is stored")
  - `test_ingest_twice_does_not_duplicate` (scenario "Second run does not duplicate")
  - `test_ingest_missing_file_fails_and_keeps_index` (scenario "Missing file")
- [x] 3.2 Add `test_ingest_real_corpus_indexes_25_documents` (scenario "Real corpus produces one indexed document per id"), using fake embeddings and skipped when `nimbo-help-center/` is absent. It also asserts the "Fee table row is preserved" line in the real NIM-020. Verify that it passes locally.
- [x] 3.3 Document the ingestion command (prerequisites, env vars, re-run semantics) in README.md. Verify that the documented command ingests the real corpus with real OpenAI embeddings.

## 4. Support chat API

- [x] 4.1 Implement `nimbo/rate_limit.py` (sliding window, injectable clock, 10 requests / 60 s per key, returns retry-after seconds). Verify with these unit tests:
  - `test_rate_limiter_rejects_eleventh_request`
  - `test_rate_limiter_is_per_ip` (scenario "Limit is per IP")
  - `test_rate_limiter_window_expires` (scenario "Window expires")
  - `test_rate_limiter_retry_after_seconds`
- [x] 4.2 Implement `nimbo/chat.py`: embed question → top-k retrieval → prompt (documents with ids; answer only from them, in the question's language, plain text, explicit no-information) → JSON parsed into `{answer, source_ids, has_information}` → filter/de-duplicate ids against retrieved docs → map to titles. Verify through the 4.3 API tests.
- [x] 4.3 Implement `nimbo/api.py`: `create_app()` (fresh rate limiter per app), `POST /api/chat`, validation model, rate-limit middleware running before body parsing, `get_chat_model` / `get_embeddings` dependencies, 503 mapping, CORS from `CORS_ORIGINS`. Verify with `TestClient` + dependency overrides (fake chat model returning JSON, counting fake embeddings) against `nimbo_test` using these tests:
  - `test_chat_returns_answer_and_sources` (scenario "Successful answer")
  - `test_chat_requests_are_independent` (scenario "Requests are independent")
  - `test_chat_rejects_blank_question` (scenario "Empty question")
  - `test_chat_rejects_question_over_500_chars` (scenario "Too long question")
  - `test_chat_accepts_question_of_500_chars` (scenario "Maximum length accepted")
  - `test_chat_rejects_non_string_question` (scenario "Non-string question")
  - `test_chat_sources_include_titles_without_duplicates` (scenario "Cited sources are returned with titles")
  - `test_chat_drops_unretrieved_source_ids` (scenario "Unknown ids are dropped")
  - `test_chat_no_information_returns_empty_sources` (scenario "No-information answer has no sources")
  - `test_chat_rate_limit_rejects_eleventh_request` (scenario "Eleventh request in a minute is rejected")
  - `test_chat_returns_503_when_model_fails` (scenario "Model provider unavailable")
  - `test_chat_embeds_only_question` (corpus-ingestion scenario "Chat request embeds only the question")
- [x] 4.4 Document how to run the API (`uvicorn`) and its contract summary in README.md. Verify that the documented command serves `POST /api/chat` locally with real OpenAI.

## 5. Answer-quality evals

- [x] 5.1 Implement `backend/evals/run_evals.py`: create the LangSmith dataset `support-chat-answers` if it is missing and run the real chain with a code evaluator (expected source ids ⊆ returned; empty for out-of-scope) and an LLM-as-judge evaluator (grounded, language, explicit no-information, plain text). Dataset examples, each tracing to its scenario:
  - `fee-instant-withdrawal-es` (scenarios "Fee question answered from the fee document", "Spanish question")
  - `fee-instant-withdrawal-en` (scenario "English question")
  - `2fa-steps-es` (scenario "Step-by-step answer")
  - `out-of-scope-capital` (scenario "Question outside the help center")
  - `seller-did-not-ship-es`, `money-on-hold-es` (the remaining suggested questions)
  - `2fa-steps-es` also traces to scenario "Voseo in Spanish answer"; the judge checks voseo on every Spanish example
  - `withdrawal-minimum-all-countries-es` (scenario "Fee minimum by country")
  - `withdrawal-minimum-chile-es` (scenario "Country given")
  - `mixed-partial-question-es` (scenario "Mixed question")
  - `declined-payment-my-account-es` (scenario "Account-specific question")
  - `card-number-in-question-es` (scenario "Card number in question"; the code evaluator also asserts that the number is absent from the answer)
  - `out-of-scope-capital` also traces to the no-invented-contact-channel rule (checked by the judge)
  - `receive-money-fee-en`, `close-account-with-balance-en` (scenario "English question"; English regressions found by task 7.1)
  Verify that the script runs and its results appear in LangSmith; record the first run's scores in README.md.

## 6. Frontend

- [x] 6.1 Scaffold `frontend/` with `create-next-app` (TypeScript strict, Tailwind, ESLint, App Router) and add `@playwright/test` with projects at 375 px and 1440 px and `NEXT_PUBLIC_API_URL` in `frontend/.env.example`. Verify that `npm run lint`, `npx tsc --noEmit` and `npm run build` pass.
- [x] 6.2 Implement the chat page per the `support-chat-ui` spec: header, input (`maxLength=500`), suggestion buttons below the input in one column, conversation list with plain-text answers and sources (no links), sensitive data notice, fictional company footer, pending state, error messages, responsive container. Verify with Playwright tests in `frontend/e2e/chat.spec.ts` (`/api/chat` intercepted with `page.route`):
  - "shows title and subtitle" (scenario "Header is visible")
  - "sends question on Enter" (scenario "Send with Enter")
  - "does not send blank question" (scenario "Blank question is not sent")
  - "caps input at 500 characters" (scenario "Length cap")
  - "shows suggested questions in order below input" (scenario "Suggestions shown on empty input")
  - "hides suggestions while typing" (scenario "Suggestions hidden while typing")
  - "shows suggestions again when input is cleared" (scenario "Suggestions return when input is cleared")
  - "clicking a suggestion sends it" (scenario "Click sends the suggestion")
  - "shows answer with sources" (scenario "Answer with sources")
  - "renders answer markup as text" (scenario "Answer markup is not rendered")
  - "clears input after sending" (scenario "Input clears after sending")
  - "does not send while an answer is pending" (scenario "No double send")
  - "shows sensitive data notice" (scenario "Notice is visible")
  - "shows fictional company footer" (scenario "Footer notice is visible")
  - "shows rate limit message on 429" (scenario "Rate limited")
  - "shows generic error on failure" (scenario "Server error", covering 503 and an aborted request)
  - "has no horizontal scroll at phone width" (scenario "Phone width", 375 px project)
  - "centers content at desktop width" (scenario "Desktop width", 1440 px project)
- [x] 6.3 Document the frontend commands (dev, lint, type-check, e2e) in README.md. Verify that each runs as written in PowerShell.

## 7. End-to-end integration check

- [x] 7.1 With Docker, the ingested real corpus, the API and the frontend running, use a phone-sized and a desktop browser window to ask the four suggested questions and one English question. Verify that each answer shows sources and that an out-of-scope question shows the no-information answer with no sources.
- [x] 7.2 Run `openspec validate add-chatbot --strict` and the full quality gate (ruff, mypy, pytest, ESLint, `tsc --noEmit`, Playwright). Verify that all pass.
