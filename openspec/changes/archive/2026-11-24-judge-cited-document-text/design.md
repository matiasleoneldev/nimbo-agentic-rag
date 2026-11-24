# Design

## Context

- `graded` (`backend/evals/run_evals.py`) returns `ask(...).model_dump()`, which is `answer` plus `sources` as `[{id, title}]`, plus the graph state's `searches`. The `answers` target calls it once. The `converse` target, used by the conversations and small-talk datasets, calls it for the graded question after the earlier turns.
- The graph state's `documents` (`nimbo/chat.py`) holds every document retrieved for the current question, once per id, as `Document`s. Their `page_content` is exactly what the agent read: the manifest header (id, title, category, products, countries) plus the PDF text, the same text `ingest` indexed. The state is reset by each `ask`, so after the graded question it holds only that question's documents.
- `agent` keeps only cited ids that are in `documents`. So every cited id has its text in the state.
- `make_judge(model, reasoning_effort, key_suffix)` came from `switch-eval-judge-gpt-6-luna`, task 2.1. Its prompt lists `Cited sources: {outputs['sources']}`.
- Re-evaluating an existing experiment with `client.evaluate(<experiment>, evaluators=[...], disable_evaluator_tracing=True)` adds feedback and creates no traces (`switch-eval-judge-gpt-6-luna`, spike check (d)).

## Goals / Non-Goals

**Goals:**
- The judge grades `grounded` against the text the answer was built from.
- Separate the effect of the text from agent variance, on the same outputs.

**Non-Goals:**
- Re-judging past experiments with the text. Their outputs do not have it, and a lookup would not be what the agent saw.
- Changing the `grounded` criterion's wording. It already says "only facts from the cited documents". The judge now has them.

## Decisions

1. **`graded` adds `cited_documents: [{id, text}]` to the outputs.** It takes the cited ids in `sources` order, and the `page_content` of the matching `Document` in the state's `documents`. The `answer` and `sources` keys stay, so the existing code evaluators do not change.
   - Alternative: adding all retrieved documents. Rejected, because the criterion is about the cited ones, and the input would grow with documents the answer did not use.
   - Alternative: the text in `sources`. Rejected, because `sources` mirrors the API's `ChatAnswer` shape.

2. **The judge prompt gains a `Cited documents:` block only when `cited_documents` is non-empty.** Each document is in a `<document id="...">` element, the format the agent sees. `Cited sources: [...]` stays. When the list is empty or missing, the prompt is character for character today's. That keeps answers without sources comparable, and lets a judge without the text be run on the new outputs by passing an empty list (decision 4). The judge reads `outputs.get("cited_documents", [])`, so it still runs on experiments from before this change.

3. **A dropped cited id is an error.** If a cited id has no document in the state, `graded` raises. That cannot happen while `agent` keeps its filter, and a silent gap would make the judge fail `grounded` for the wrong reason.

4. **The comparison is a throwaway script** in the scratchpad, never committed. It runs on the three new experiments with `disable_evaluator_tracing=True`. Each pass is wrapped in `get_usage_metadata_callback` for tokens, and feedback is read one run at a time (the `switch-eval-judge-gpt-6-luna` calibration found that a single query over all runs is incomplete). It runs two `gpt-4.1-mini` judges with suffixed keys:
   - `@no-text`: the judge called with `cited_documents` emptied. This is the old prompt on the new outputs.
   - `@text`: the same judge as the run, re-run. Its disagreement with the stored verdict is the noise floor with the text.

   It writes a CSV with every row where `@no-text` and the stored verdict differ, or where `grounded` fails, together with the cited documents' ids and the comments.

5. **README.** The eval section says that the judge reads the text of the cited documents since this change, and that pass rates before it were judged without that text.

## Risks / Trade-offs

- [Stricter `grounded` turns up real agent defects, and pass rates drop] → That is the point of the change. Every failure is reviewed and recorded. Fixing the agent is a later change.
- [Long documents raise the judge's input tokens] → Measured per call (decision 4). Only cited documents are added. The judge's cost per run stays small next to the agent's.
- [The judge may fail facts that the agent inferred correctly from the text (arithmetic, a translation into English)] → Shows up as `grounded` failures in the review and is recorded as a judge miss. The prompt is not changed in this change.
- [The new run's outputs differ from the old run's by agent variance] → The `@no-text` pass on the same outputs separates the text's effect from the variance.
- [Bigger outputs in the LangSmith traces] → The corpus is synthetic, and the traces already hold the same text in the agent's tool messages.

## Migration Plan

- Rollback: revert `run_evals.py` (no `cited_documents` in the outputs, no documents block in the prompt). Experiments made in between keep their extra key, which nothing else reads.
- Order: this change lands first. `switch-eval-judge-gpt-6-luna` then resumes at its task 3.1a, on this change's experiments.

## Results

Task 2.1, 2026-11-24. `gpt-6-luna` (`none`), `k=4`, `max_searches=3`, 3 repetitions, judge `gpt-4.1-mini` with the cited documents' text. Next to it, the last full run judged without the text (2026-11-09).

| Metric | answers (with text) | answers (before) | conversations (with text) | conversations (before) | small talk (with text) | small talk (before) |
|---|---|---|---|---|---|---|
| sources | 75/75 | 75/75 | 27/27 | 27/27 | 41/41 | 42/42 |
| no_forbidden_text | 75/75 | 75/75 | 27/27 | 27/27 | 42/42 | 42/42 |
| searched | 72/72 | 72/72 | 24/24 | 24/24 | 18/18 | 18/18 |
| skipped_search | - | - | - | - | 23/23 | 23/24 |
| search_count (mean) | 1.48 | 1.59 | 1.19 | 1.22 | 0.51 | 0.64 |
| grounded | 75/75 | 74/75 | 27/27 | 27/27 | 41/41 | 42/42 |
| correct_language | 75/75 | 75/75 | 27/27 | 27/27 | 41/41 | 42/42 |
| voseo | 54/54 | 53/54 | 26/27 | 27/27 | 27/29 | 29/30 |
| plain_text | 75/75 | 75/75 | 27/27 | 27/27 | 41/41 | 42/42 |
| meets_expectation | 75/75 | 74/75 | 27/27 | 27/27 | 40/41 | 41/42 |

- Experiments: `agentic-gpt-6-luna-none-k4-s3-bb70fb80`, `-conversations-533917b2` and `-small-talk-d821445b`. Before: `-d0901026`, `-conversations-2d44876e` and `-small-talk-753e4ee9`.
- Every root run without a target error has `cited_documents`, one per cited source.
- One target error in small talk: the model returned two JSON objects one after the other ("trailing characters at line 2"). This is the known defect recorded in `switch-eval-judge-gpt-6-luna`'s predecessor `switch-chat-model-gpt-6-luna` (design.md, Baseline). It predates this change. Its row has no judge verdict, so small talk totals are 41 instead of 42.

Task 2.2, 2026-11-24. The three experiments above, re-evaluated with two suffixed `gpt-4.1-mini` judges (design.md, decision 4). No run was created in the experiments' projects, in `evaluators` or in the default project. The row with the target error has no verdicts and is left out (143 rows; `voseo` counts Spanish rows only).

| Metric | `@no-text` differs from stored | `@text` (re-run) differs from stored |
|---|---|---|
| grounded | 0/143 | 0/143 |
| correct_language | 0/143 | 0/143 |
| voseo | 4/110 | 5/110 |
| plain_text | 0/143 | 0/143 |
| meets_expectation | 0/143 | 1/143 |

- Judge tokens per call, mean over 144 calls (input / output): without the text 482 / 144; with the text 1,268 / 160. The input grows about 2.6×. Part of it was served from OpenAI's prompt cache (78,336 of 182,595 input tokens).
- With or without the text, `gpt-4.1-mini` passes `grounded` on every row. The text does not change its verdicts. Its `voseo` verdicts vary by about 4–5 rows in 110 between runs, with or without the text.

Task 2.3, 2026-11-24. The review CSV had 4 rows (every row where `@no-text` differs from the stored verdict, plus every `grounded` failure, of which there were none).

- `follow-up-out-of-scope-es` rep 2 ("El centro de ayuda no tiene información…"), `farewell-es` rep 2 ("¡Chau!") and `thanks-after-answer-es` rep 2 ("¡De nada!"): the stored `voseo` is a fail. These are judge misses: the answers have no tú-only or usted forms. These are the known `gpt-4.1-mini` false negatives.
- `greeting-es` rep 1 ("¿En qué te puedo ayudar?"): `@no-text` fails `voseo`, and the stored verdict passes. This is a judge miss: "te" is a form shared by voseo and tú, which the criterion passes.
- Agent defects: none. Judge misses: 4, all `voseo`, none related to the document text.

Outcome (2026-11-24): **accepted as the new baseline.** The judge now reads the cited documents' text. On `gpt-4.1-mini` this changes no verdict, because it already passed `grounded` everywhere. The text is the evidence a stricter judge needs, which `switch-eval-judge-gpt-6-luna` measures next (its task 3.1a, on these three experiments).
