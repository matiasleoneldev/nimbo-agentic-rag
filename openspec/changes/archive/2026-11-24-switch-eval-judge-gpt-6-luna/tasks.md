# Tasks

Unless a task says otherwise, verify the backend tasks with `poetry run ruff format . ; poetry run ruff check . ; poetry run mypy . ; poetry run pytest` in `backend/`, with `docker compose up -d db` running. Tasks marked **manual** call the real OpenAI API and cost credits. The author runs them, and they never go into pytest.

This change has no spec deltas (`skip_specs: true`). The judge is eval tooling, so no spec scenario traces to it.

## 1. Spike (before any code change)

- [x] 1.1 **Manual spike**: a throwaway script in the scratchpad, not committed. Run checks (a) to (d) of design.md, decision 3, on 3 rows of the latest full `agentic-gpt-6-luna-none-k4-s3` experiment. Record the results, the token counts per effort and any warnings under `## Spike findings` in design.md, with the names of the experiments the calibration will use. If (a), (b) or (d) fails, stop and revise proposal.md and design.md before group 2; if only (a) fails, drop the `low` candidate. Verify that `## Spike findings` has one line per check.

## 2. Configurable judge (still on `gpt-4.1-mini`)

- [x] 2.1 In `backend/evals/run_evals.py`, replace `judge` with `make_judge(model, reasoning_effort, key_suffix="")` (design.md, decision 1), add the constants `JUDGE_MODEL = "gpt-4.1-mini"` and `JUDGE_REASONING_EFFORT: str | None = None`, and pass `make_judge(JUDGE_MODEL, JUDGE_REASONING_EFFORT)` to `_run`. Add `judge: {model, reasoning_effort}` to the experiment metadata (decision 6). The prompt, `Verdict` and the unsuffixed feedback keys stay as they are. Verify with the full backend gate, and with `poetry run python -m evals.run_evals --dataset small-talk --repetitions 1` (**manual**): the experiment's metadata shows the judge, and its feedback keys are the same as before.

## 3. Calibration

- [x] 3.1 **Manual**: the throwaway calibration script of design.md, decision 4, on the three experiments named in `## Spike findings`. Verify that each experiment's rows carry the three suffixed key sets, that the project's trace count did not change, and that the review CSV is in the scratchpad.
- [x] 3.1a **Manual**: after the cited-document-text change is archived, repeat 3.1 on its first full experiments (they carry the cited documents' text and a `gpt-4.1-mini` baseline). Record the new experiment names, the disagreement table and the tokens per call under `## Calibration`, after the pause note. Verify that the rows carry the three suffixed key sets and that no judge call failed.
- [x] 3.2 **Manual**: review every disagreement row of a candidate in the CSV and mark which judge is right. Under `## Calibration` in design.md, record per metric and judge: the disagreement rate against the stored verdict, the `@gpt-4.1-mini` noise floor, the reviewed rights and wrongs, any `grounded` false pass, tokens per call (input, output, reasoning) and the failed judge calls. Apply the acceptance rule in proposal.md and record the outcome, dated. Verify that the outcome line names the accepted judge (model and effort) or says that `gpt-4.1-mini` stays.

## 4. Switch

- [x] 4.1 If 3.2 accepted a candidate, set `JUDGE_MODEL` and `JUDGE_REASONING_EFFORT` to it in `backend/evals/run_evals.py`, and verify with the full backend gate. Otherwise mark this task done with no change, and note that in `## Calibration`.
- [x] 4.2 Update the judge line of the eval section in `README.md`: the judge model and effort, the switch date, that pass rates before that date were measured by `gpt-4.1-mini`, and a pointer to this change's design.md. Verify that the model and effort it shows match the constants in `run_evals.py`.

## 5. Integration check

- [x] 5.1 **Manual**: run `poetry run python -m evals.run_evals` (all datasets, 3 repetitions) with the accepted judge. This run is the new judge's baseline, not a gate (proposal.md, Acceptance). Verify that the three experiments' metadata names the judge and that no judge call fails. Record the pass rates under `## Calibration`, with every failure reviewed and marked as a real agent defect (for a later change) or a judge miss.
