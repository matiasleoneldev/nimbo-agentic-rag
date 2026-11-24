# Proposal

## Why

The LLM judge in `backend/evals/run_evals.py` grades `grounded` ("only facts from the cited documents") from the cited sources' ids and titles alone, never their text. So it can only judge plausibility. The calibration of `switch-eval-judge-gpt-6-luna` (paused, see its design.md, `## Calibration`) showed the cost. On the same 144 rows, `gpt-6-luna` failed `grounded` on 23–29 rows because it could not verify the facts, including facts that are in the cited document. `gpt-4.1-mini` passed all of them. Until the judge sees the evidence, no judge comparison can be trusted on the metric that matters most.

## What Changes

- The eval target's outputs gain the text of the documents the answer cites, exactly as the agent retrieved them: the graph state's `documents`, filtered to the cited ids. A lookup by id at judge time was rejected, because it reads the current index rather than what the agent saw. (Decided 2026-11-24.)
- The judge prompt includes the cited documents' text when there is any. With no cited documents (small talk, out of scope), the prompt is the same as today. The `Verdict` criteria do not change. (Decided 2026-11-24.)
- The judge stays `gpt-4.1-mini`. Switching it is the paused change, which resumes after this one with a calibration on this change's experiments. (Decided 2026-11-24.)
- Measurement (Decided 2026-11-24):
  - A new full run (all three datasets, 3 repetitions, 144 agent traces) is the new baseline of the evals.
  - The same experiments are re-evaluated with the judge without the document text, under its own feedback keys. No agent run and no traces are needed. That isolates the effect of the text from agent variance.
  - Judge tokens per call are recorded with and without the text, since the input grows.
- Acceptance (Decided 2026-11-24): the new run is a baseline, not a gate, like the first run of a new judge in `switch-eval-judge-gpt-6-luna`. Every `grounded` failure, and every row where the verdicts with and without the text differ, is reviewed. Each is recorded as an agent defect (for a later change) or a judge miss.
- Out of scope (Decided 2026-11-24): switching the judge model, changing the `Verdict` criteria or other prompt wording, passing retrieved but uncited documents, the agent's behavior, and guardrails.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The judge and the eval target's outputs are offline eval tooling. No spec names them, and no API, page or answer behavior changes. The change sets `skip_specs: true`.

## Impact

- `backend/evals/run_evals.py`: the eval target's outputs (`graded`) and the judge prompt (`make_judge`). It builds on the `make_judge` refactor from `switch-eval-judge-gpt-6-luna` (task 2.1, done and not yet committed).
- `README.md`: the eval section says that the judge reads the cited documents, and that pass rates before this change were judged without them.
- No new dependency. No app, API, page, database or test change.
- Cost: 144 agent traces for the new baseline, and about 288 `gpt-4.1-mini` judge calls for the comparison. The judge's input tokens grow by the cited documents' length.
