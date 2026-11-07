# Tasks

Unless a task says otherwise, verify the backend tasks with `poetry run ruff format . ; poetry run ruff check . ; poetry run mypy . ; poetry run pytest` in `backend/`, with `docker compose up -d db` running. Tasks marked **manual** call the real OpenAI API and cost credits. The author runs them, and they never go into pytest.

This change has no spec deltas (`skip_specs: true`). The new eval examples measure existing requirements, as listed in design.md, decision 6.

## 1. Spike (before any code change)

- [x] 1.1 **Manual spike**: a throwaway script in the scratchpad, not committed. Bind `ChatOpenAI(model="gpt-6-luna", reasoning_effort="none", use_responses_api=False)` exactly as the `agent` node does, and run checks (a) to (f) of design.md, decision 3. Record the results, token counts and any warnings under `## Spike findings` in design.md. If any of (a) to (e) fails, stop and revise proposal.md and design.md before group 2. Verify that `## Spike findings` has one line per check.

## 2. Configuration option, eval examples and baseline (still on `gpt-4.1-mini`)

- [x] 2.1 Add an optional `chat_reasoning_effort: str | None` to `Settings` (`nimbo/config.py`), read from `models.chat_reasoning_effort` and `None` when the key is absent. Document the key with a comment in `backend/app.yaml`, left unset for now. In `nimbo/api.py`, `get_chat_model` returns `ChatOpenAI(model=..., reasoning_effort=settings.chat_reasoning_effort, use_responses_api=False)`, with a one-line comment on why it pins Chat Completions (design.md, decision 2). Extend `tests/test_config.py` to assert `chat_reasoning_effort is None`. Verify with the full backend gate.
- [x] 2.2 In `backend/evals/run_evals.py`:
  - Add the three answer examples and the conversation example of design.md, decision 6, after checking each expectation against the PDF text (`nimbo.pdf_text`) and each required id against `manifest.json`.
  - Change the experiment prefix to `agentic-<chat model>[-<effort>]-k<k>-s<max_searches>`, and add `chat_reasoning_effort` to the experiment metadata (decision 5).

  Verify with ruff and mypy. No pytest change is needed.
- [x] 2.3 **Manual**: run `poetry run python -m evals.run_evals` with `gpt-4.1-mini`. Record the two experiment names, the per-metric pass rates, `search_count`, p50 latency and tokens per run under `## Baseline` in design.md, with the per-example failures. Verify that both experiments appear in LangSmith with 3 repetitions.

## 3. Switch to `gpt-6-luna` and measure

- [x] 3.1 In `backend/app.yaml`, set `models.chat: gpt-6-luna` and `models.chat_reasoning_effort: none`, and update the comment. Change the assertion in `tests/test_config.py` to `chat_reasoning_effort == "none"`. Verify with pytest.
- [x] 3.2 **Manual**: run `poetry run python -m evals.run_evals`. Verify that the experiments are named `agentic-gpt-6-luna-none-k4-s3` and `-conversations`, and that they appear in LangSmith with 3 repetitions.
- [x] 3.3 Under `## Results` in design.md, add a table in the `agentic-rag` format (baseline row, then the `gpt-6-luna` row), plus a diagnosis of the compound examples from the `searches` outputs in LangSmith: queries per topic, and whether the four-topic example combined topics. Apply the acceptance rule in proposal.md and record the outcome, dated. If it is not met, revert 3.1 (`app.yaml` and `tests/test_config.py`) and verify with pytest. Verify that the outcome line names the accepted model.
- [x] 3.4 Update `README.md`: the experiment naming (with the effort), the number of examples per dataset, the current chat model, and a short results note pointing to this change's design.md. Verify that every command and name it shows matches `run_evals.py` and `app.yaml`.

## 4. Integration check

- [x] 4.1 **Manual**: with the accepted model, start the API (`poetry run uvicorn nimbo.api:create_app --factory --port 8000`) and the page (`npm run dev`). Ask "¿Cuánto cuesta un retiro inmediato y cuánto tarda?" and one English question. Verify that the answer streams progressively, that sources are shown, and that no search query appears in the page.
