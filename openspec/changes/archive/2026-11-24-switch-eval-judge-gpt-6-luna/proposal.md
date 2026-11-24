# Proposal

## Why

The LLM judge in `backend/evals/run_evals.py` is still `gpt-4.1-mini`, while the chat model moved to `gpt-6-luna` on 2026-11-07. The judge has known misses: in `small-talk-without-search` it failed `voseo` on answers its own comment called fine. `gpt-6-luna` is newer, and its list price is lower than `gpt-4.1-mini`'s. A better judge is also needed before the planned guardrails change, which will need its own evals.

## What Changes

- The judge changes from `gpt-4.1-mini` to `gpt-6-luna`, only if the calibration passes the acceptance rule below. (Decided 2026-11-24.)
- Two candidates are measured: `gpt-6-luna` with `reasoning_effort: none` and with `low`. The judge binds no tools, so the Chat Completions limit to `none` (which applies when tools are bound) does not apply to it. `low` is the starting point; `none` is measured to separate the gain from the newer model from the gain from reasoning. Higher efforts are not measured. (Decided 2026-11-24.)
- A throwaway spike runs first: `Verdict` structured output on `gpt-6-luna` with `low` on Chat Completions, reasoning token counts, and whether re-evaluating an existing experiment honors `disable_evaluator_tracing`. If it fails, this proposal and the design are revised before any code changes. (Decided 2026-11-24.)
- Calibration re-evaluates the latest full `agentic-gpt-6-luna-none-k4-s3` experiments (answers, conversations, small talk: 48 examples × 3 repetitions = 144 rows) instead of running the agent again. (Decided 2026-11-24.)
  - The `gpt-4.1-mini` verdicts already stored on those rows are the reference.
  - `gpt-4.1-mini` is re-run once on the same rows to measure its own noise. A disagreement rate inside that noise means the two judges are equivalent.
  - Each judge writes its own feedback keys, so verdicts do not mix.
  - No new agent traces. Judge calls are about 3 × 144 = 432 OpenAI calls.
- Acceptance (Decided 2026-11-24, before any calibration run):
  - The author reviews every row where a candidate and the stored `gpt-4.1-mini` verdict disagree, and marks which judge is right.
  - A candidate is rejected if it passes `grounded` on any row the author marks as not grounded. The judge would grade its own chat model's answers, so a false pass on grounding is the self-preference failure this change must rule out.
  - A candidate is rejected if it is wrong on more reviewed disagreements than `gpt-4.1-mini`, counted in total across all metrics, not per metric. (Decided 2026-11-24.) Rows the author cannot decide are left out of the counts.
  - Between accepted candidates, `none` wins if it is right on at least as many reviewed disagreements as `low` (no reasoning tokens, and the binding is already proven); otherwise `low` wins.
  - A tie with `gpt-4.1-mini` is accepted, as in `switch-chat-model-gpt-6-luna`: the same quality on a newer, cheaper model.
  - If no candidate is accepted, the judge stays `gpt-4.1-mini`, and the calibration results stay in design.md.
  - The first full run with the new judge is its baseline, not a gate. (Decided 2026-11-24.) Every failure in it is reviewed and recorded. A failure the author confirms as real is an agent defect for a later change, not a reason to revert the judge.
- Experiment metadata records the judge model and effort, so pass rates measured by different judges can be told apart. (Decided 2026-11-24.)
- Out of scope (Decided 2026-11-24): passing the cited documents' text to the judge (a separate later change, since it changes what `grounded` measures), guardrails (a separate later change), other judge models (`gpt-6-sol`, `gpt-6.1-terra`), changes to the `Verdict` criteria or the judge prompt, and re-running the agent.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The judge is offline eval tooling. No spec names the judge, and no API, page or answer behavior changes. The change sets `skip_specs: true`.

## Impact

- `backend/evals/run_evals.py`: the judge's model and effort, and the experiment metadata.
- `README.md`: the eval section names the judge model.
- No new dependency: `langchain-openai` 1.6.7 already supports `reasoning_effort`, and `langsmith` 0.14.4 can re-evaluate an existing experiment.
- No app, API, page, database or test change.
- Cost: the calibration's judge calls, at `gpt-6-luna`'s $0.10 input / $0.50 output per 1M tokens (OpenAI pricing page, 2026-11-07). Reasoning tokens bill as output and are recorded.
- Risk: `gpt-6-luna` has no dated snapshot, so the judge can change when OpenAI updates the model.
