# Tasks

Unless a task says otherwise, verify the backend tasks with `poetry run ruff format . ; poetry run ruff check . ; poetry run mypy . ; poetry run pytest` in `backend/`, with `docker compose up -d db` running. Tasks marked **manual** call the real OpenAI API and cost credits. The author runs them, and they never go into pytest.

Scenario traceability:
- "Small talk":
  - Greeting: LangSmith `support-chat-small-talk` / `greeting-es`.
  - Thanks after an answer: `thanks-after-answer-es`.
  - What the chat can do: `capabilities-es`.
  - Greeting with a question: `greeting-with-question-es`.
  - Thanks with a follow-up: `thanks-with-follow-up-es`.
  - Account question is not small talk: `can-you-see-my-account-es`.
- "Answers are grounded in help-center documents": the scenarios are unchanged and keep their existing evals in `support-chat-answers` and `support-chat-conversations`.
- "Help-center searches":
  - Answer without a search has no sources: pytest `test_chat_answer_without_search_has_no_sources`.
  - Search limit: `test_chat_stops_searching_at_limit`.
  - The other scenarios are unchanged and keep their existing tests and evals.

## 1. Small-talk evals and the baseline (code still forces the first search)

- [x] 1.1 In `backend/evals/run_evals.py`, following design.md, decisions 3 and 4:
  - Add `small_talk: bool = False` to `_example`.
  - Make `searched` skip `small_talk` examples.
  - Add the `skipped_search` evaluator and register it in `_run`.
  - Make `sources` expect empty `sources` for `small_talk`.
  - Add `SMALL_TALK_DATASET = "support-chat-small-talk"` with the 14 examples of decision 3, run with the `converse` target. Check each expectation against the PDF text (`nimbo.pdf_text`) and each id against `manifest.json` first.
  - Update the module docstring (three datasets).
  - Add `--dataset` (repeatable) and `--repetitions` (default 3) arguments (design.md, decision 5).

  Verify with ruff and mypy, and check that the existing examples' reference outputs only gain `small_talk: false`.
- [x] 1.2 **Manual**: run `poetry run python -m evals.run_evals` on the current code. Under `## Baseline` in design.md, record the pass rates and `search_count` of the three datasets (from the full run of 2026-11-09), and for the small-talk experiment, run alone with `--dataset small-talk`, its name, p50 latency and tokens per run. Split the small-talk dataset into small-talk and boundary examples, and list the per-example failures. Verify that `skipped_search` is 0% (the forced first search) and that the small-talk experiment appears in LangSmith with 3 repetitions.

## 2. Free first turn and the small-talk prompt rule

- [x] 2.1 In `nimbo/chat.py`, bind `tool_choice="none"` at the search limit and leave it unset otherwise (design.md, decision 1). Replace the "first turn must search" comment with the reason for leaving it unset. In `tests/test_chat_api.py`:
  - Replace `test_chat_first_turn_must_search` with `test_chat_first_turn_does_not_force_search`, which asserts the bound `tool_choice` values are `[None, None]`.
  - Change the assertion in `test_chat_stops_searching_at_limit` to `[None, None, None, "none"]`.
  - Reword the comment in `test_chat_answer_without_search_has_no_sources`: answering without a search is now allowed, and the filter keeps such an answer source-free.

  Verify with the full backend gate.
- [x] 2.2 Add the small-talk rule to `SYSTEM_PROMPT`, and the small-talk exception to the "help center does not have that information" rule (design.md, decision 2). Verify with the full backend gate, and check that no test asserts on the prompt text.
- [x] 2.3 **Manual**: run `poetry run python -m evals.run_evals`. Under `## Results` in design.md:
  - Add a table in the format of the previous change: the baseline row, then this change's row, for each dataset.
  - Add the savings of decision 6, and a diagnosis of every failing example from its `searches` output.
  - Apply the acceptance rule in proposal.md and record the outcome, dated.
  - If the rule is not met, allow one prompt iteration (2.2 then 2.3 again), recorded as its own row. If it is still not met, revert 2.1 and 2.2, and revise the "Small talk" requirement and proposal.md so they describe the forced search.

  Verify that the outcome line states whether the free first turn was kept, and that it reports `searched` and `skipped_search` at 100%.
- [x] 2.4 Update `README.md`:
  - The "How a question is answered" paragraph: small talk is answered without a search, and every other question is searched first.
  - The eval section: three datasets with their example counts, and `skipped_search` under scoring.
  - A short results note pointing to this change's design.md.

  Verify that every dataset name, count and command it shows matches `run_evals.py`.

## 3. Integration check

- [x] 3.1 **Manual**: start the API (`poetry run uvicorn nimbo.api:create_app --factory --port 8000`) and the page (`npm run dev`). Ask "Hola", then "Hola, ¿cuánto cuesta un retiro inmediato?". Verify on the page that:
  - the first answer streams and shows no source list;
  - the second shows NIM-020.

  Verify in LangSmith that the first trace has no `search` node.
  - Done 2026-11-09 by the author's decision. Verified on the page: "Hola" got an answer without a source list, and the second question showed NIM-020 and NIM-021. The LangSmith trace was not inspected, because the monthly trace limit was exceeded and the API traces were not recorded. `skipped_search` 24/24 in the evals covers the same claim.
