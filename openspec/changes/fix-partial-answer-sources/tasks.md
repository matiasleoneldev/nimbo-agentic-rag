# Tasks

## 1. Coverage in the model output

Unless a task says otherwise, verify with `poetry run ruff format . ; poetry run ruff check . ; poetry run mypy . ; poetry run pytest` in `backend/`, with `docker compose up -d db` running.

- [x] 1.1 In `backend/nimbo/chat.py`:
  - In `ModelAnswer`, replace `has_information: bool` with `coverage: Literal["full", "partial", "none"]`, declared after `answer` and before `source_ids`.
  - In `SYSTEM_PROMPT`, the partial-answer rule ends with "and set coverage to partial". The no-information rule says "set coverage to none". The `source_ids` rule says "empty if coverage is none".
  - In `generate`, empty the ids only when `parsed.coverage == "none"`.

  Verify that `grep -rn has_information backend/nimbo backend/tests` returns nothing once 1.2 is done.
- [x] 1.2 In `backend/tests/fakes.py`, change `model_reply(answer, source_ids, has_information=True)` to `model_reply(answer, source_ids, coverage="full")`, typed with the same `Literal`, and emit `coverage` in the JSON.
- [x] 1.3 No-information answer / No-information answer has no sources → update `test_chat_no_information_returns_empty_sources` in `backend/tests/test_chat_api.py` so the fake replies with `coverage="none"` and still cites NIM-020. Verify that `sources` is `[]`.
- [x] 1.4 Partially covered questions / Partial answer keeps its sources → add `test_chat_partial_answer_keeps_sources` in `backend/tests/test_chat_api.py`. The fake replies with `coverage="partial"` and cites NIM-020. Verify that `sources` is `[{"id": "NIM-020", "title": ...}]`.

## 2. Answer quality

- [x] 2.1 Partially covered questions / Mixed question → LangSmith dataset `support-chat-answers`, example `mixed-partial-question-es`. No-information answer / Question outside the help center → same dataset, example `out-of-scope-capital`. Run `poetry run python -m evals.run_evals` once, then ask the mixed question 4 more times against the real model, with an unsaved snippet that calls the API. Record the result in this task as "Result YYYY-MM-DD: ...". Done when:
  - `sources` includes NIM-020 in 5 runs out of 5 (baseline 2026-10-24: 3 out of 5).
  - `out-of-scope-capital` and `follow-up-out-of-scope-es` still pass `sources`.
  - Every other metric has no regression.

  If the mixed question still fails, record it and keep the README note (2.2). Do not add another fix inside this change.

  Result 2026-10-25: `mixed-partial-question-es` had NIM-020 in `sources` in 5 runs out of 5 (1 eval run + 4 extra API calls; baseline 3 out of 5). Eval run: `support-chat-answers` and `support-chat-conversations` passed every metric (sources 16/16 and 8/8, so `out-of-scope-capital` and `follow-up-out-of-scope-es` still pass; no regression in the other metrics).
- [x] 2.2 Update the known-flaky note in `README.md` (the `mixed-partial-question-es` line): remove it if 2.1 passed 5 out of 5. Otherwise, replace it with the new failure rate and the cause that was observed. Verify by reading the README section.
