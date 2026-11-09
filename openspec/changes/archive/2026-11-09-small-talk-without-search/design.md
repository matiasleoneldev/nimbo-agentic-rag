# Design

## Context

- The `agent` node (`nimbo/chat.py`) binds `SearchHelpCenter` with `tool_choice="required"` while no search has run, `"none"` at the search limit, and the default otherwise. So every question gets at least one search, small talk included.
- When the model answers without a tool call, the graph already goes straight to the end. The `sources` filter already drops every id when nothing was retrieved (`test_chat_answer_without_search_has_no_sources`). The streaming path already handles a first reply that is the answer JSON. So no graph or API change is needed: only the binding and the prompt.
- `SYSTEM_PROMPT` already says to search before any question about Nimbo. It also says to answer "the help center does not have that information" for anything the results lack. Small talk has no results, so without a new rule, that is the answer it gets.
- The page (`frontend/app/chat.tsx`) renders the source list only when `sources` is non-empty.
- Evals: `run_evals.py` runs two datasets. `searched` skips `no_information` examples. `sources` expects empty `sources` for them. The `converse` target asks earlier `turns` live before the graded question.

## Goals / Non-Goals

**Goals:**
- The model decides whether to search on every turn below the limit. Small talk is answered in one model call, with no embedding.
- Measure the savings against a same-day baseline, and measure the risk of Nimbo questions answered without a search.

**Non-Goals:**
- Detecting small talk in code (regex, classifier, router). The model's own decision is the mechanism; the spec and the evals make it explicit.
- Changing what small talk looks like on the page.

## Decisions

1. **The first turn binds no `tool_choice`** (`"none"` only at the limit, otherwise the default).
   - Alternatives:
     - A `small_talk` tool: rejected in proposal.md.
     - Keeping `"required"` and adding a prompt rule: the API would still force the search, so the rule could not take effect.
     - Forcing the search only when a heuristic says "not small talk": that is a router, out of scope.
   - The `agentic-rag` reason for `"required"` was a `gpt-4.1-mini` rate (60/63). It is re-measured on `gpt-6-luna` here instead of assumed.

2. **A small-talk rule in `SYSTEM_PROMPT`, placed under "Searching"**, roughly:
   > If the message only greets, thanks, says goodbye or asks in general what you can do, and asks nothing else (a question about the visitor's account is not small talk), answer briefly without calling search_help_center, with coverage none and no source_ids. To "what can you do", say that you answer questions about Nimbo using its help center and that you cannot see any visitor's account. Never state facts about Nimbo in such an answer. If the message asks anything else as well, it is not small talk: search.

   - The existing "for anything the search results do not contain, say the help center does not have that information" rule gets an exception for small talk, so the two rules do not conflict.
   - `coverage: none` keeps `sources` empty through the existing filter, so no new field is needed in `ModelAnswer`.
   - The `SearchHelpCenter` docstring does not change.
   - Alternative: fixed template answers per kind and language. Rejected: the answer language follows the question, whatever that language is, and templates would need language detection.

3. **A separate dataset, `support-chat-small-talk`, run with the `converse` target.** `turns` is empty for single messages. That makes thanks and goodbyes after a real answer possible, which is how small talk actually arrives.
   - Separate, so the existing totals (75 and 27 graded runs) stay comparable with the 2026-11-07 results.
   - Examples. Each expectation and required id is checked against the PDF text and `manifest.json` before it is written.
     - Small talk (`small_talk=True`, no required ids):
       - `greeting-es` "Hola"
       - `greeting-en` "Hi there!"
       - `greeting-good-morning-es` "Buen día"
       - `capabilities-es` "¿Qué podés hacer?"
       - `capabilities-en` "What can you help me with?"
       - `thanks-after-answer-es`: turn "¿Cuánto cuesta un retiro inmediato?", then "¡Gracias!"
       - `thanks-after-answer-en`: turn "How much does an instant withdrawal cost?", then "Thanks, that helps."
       - `farewell-es`: turn "¿Cuánto cuesta un retiro inmediato?", then "Listo, chau"
     - Boundary (must search):
       - `greeting-with-question-es` "Hola, ¿cuánto cuesta un retiro inmediato?": NIM-020
       - `greeting-with-question-en` "Hi! How do I turn on two-step verification?": NIM-004
       - `thanks-with-follow-up-es`: turn "¿Cuál es el mínimo por retiro inmediato?", then "Gracias, ¿y en Chile?": NIM-020, 500 CLP
       - `what-can-i-do-declined-payment-es` "¿Qué puedo hacer si me rechazan un pago?": NIM-032
       - `what-can-i-do-business-account-es` "¿Qué puedo hacer con una Cuenta de Negocios?": any of NIM-050, NIM-021
       - `can-you-see-my-account-es` "¿Podés ver mi cuenta?": says the chat cannot see accounts. `searched` gates it. It gets required or any-of ids only if task 1.1 finds a document that covers the question; otherwise the judge grades the rest.
   - Expectations for small talk: a short reply in the question's language (voseo in Spanish), with no facts about Nimbo, and not a "no information" answer.

4. **Evaluators.**
   - `_example` gains `small_talk: bool = False`. Existing examples keep `False`, so the existing datasets score as before.
   - `searched` also skips `small_talk` examples.
   - A new `skipped_search` scores `small_talk` examples only: `not outputs["searches"]`.
   - `sources` expects empty `sources` when `small_talk` is set, as it does for `no_information`.
   - The judge is unchanged. Its `grounded` already passes an answer that states no facts about Nimbo, and `meets_expectation` carries the small-talk expectation.
   - Alternative: one combined "correct search decision" metric. Rejected: it would mix the gated risk (`searched`) with the reported savings (`skipped_search`).

5. **Baseline first, on the current code.** Latency and tokens are measured on the small-talk dataset only (decided 2026-11-09, to save eval credits). The first baseline run over all three datasets lost its traces to the LangSmith monthly trace limit, so for `support-chat-answers` and `support-chat-conversations` only its pass rates exist. `run_evals.py` takes `--dataset` (repeatable) and `--repetitions` (default 3). Gates count only from a full run: all three datasets, 3 repetitions; partial runs are for diagnosis and are recorded as such. With `"required"`, `skipped_search` is 0% by construction. The point of the baseline is p50 latency, tokens per run and answer quality per dataset on the same day, because `gpt-6-luna` has no dated snapshot. Both runs keep the current prefix: the configuration does not change, and LangSmith already gives every experiment a unique suffix. `## Baseline` and `## Results` record which experiment name is which.

6. **Savings metrics.** Recorded under `## Results` for the small-talk dataset, split into small-talk and boundary examples using the per-example LangSmith runs:
   - `skipped_search` rate.
   - `search_count`.
   - p50 latency and tokens per run, baseline against change.
   - Cost per small-talk question, estimated as tokens times the `gpt-6-luna` list price recorded in the previous change. The embedding cost of one short query is negligible and is not reported.

No new dependency.

## Risks / Trade-offs

- [Under-retrieval: a Nimbo question answered without a search, now that nothing forces one] → `searched` is gated at 100% on all three datasets, and the boundary examples target the likely confusions. If it fails, one prompt iteration, then revert (proposal.md, acceptance).
- [Out-of-scope questions answered from the model's own knowledge: `agentic-rag` iteration 0 answered "Canberra"] → The "never answer from your own knowledge" rule stays. `out-of-scope-capital` must pass in every repetition.
- [The "what can you do" answer invents features the chat does not have, such as account lookups or opening cases] → The prompt states the only two things to say. The judge's `meets_expectation` checks the answer, and `grounded` checks that it states no facts about Nimbo.
- [Small talk gets "the help center does not have that information"] → Low risk: the manual check on 2026-11-09 got a correct greeting with no sources, even with the forced search. The prompt exception in decision 2 stays, because it makes the prompt agree with the spec. The baseline (task 1.2) measures this on all 8 small-talk examples through the judge's small-talk expectation.
- [Without a forced search, the first reply of a Nimbo question may be the answer JSON, streamed as deltas before any search] → That is the existing "no search" path, already covered for the stream by `test_chat_stream_waits_for_parseable_reply_start` and the source filter. Nothing new is streamed.
- [Three repetitions on a small dataset are noisy] → Gates are on deterministic counts (`searched`, `skipped_search`). Judge differences of a point or two are the author's call, dated.
- [`skipped_search` gated at 100% may fail on a single greeting the model chooses to search] → That is the cheap error in cost, but it would make the spec untrue, so it gets the same prompt iteration and fallback as `searched` (proposal.md, acceptance).

## Migration Plan

No data or API migration. Rollback means restoring `"required"` on the first turn and the previous prompt. The small-talk requirement then has to be revised in this change before archiving (proposal.md).

## Baseline

Recorded 2026-11-09, on the code before task 2.1 (first turn forced to search), `gpt-6-luna`, `k=4`, `max_searches=3`, 3 repetitions.

Pass rates of the full run over the three datasets. Its LangSmith traces were lost to the monthly trace limit, so it has no latency or tokens (decision 5):

| Dataset | `searched` | `skipped_search` | `sources` | `grounded` | `no_forbidden_text` | `meets_expectation` | `search_count` |
|---|---|---|---|---|---|---|---|
| `support-chat-answers` (`agentic-gpt-6-luna-none-k4-s3-ecd5bf27`) | 72/72 | n/a | 75/75 | 75/75 | 75/75 | 75/75 | 1.59 |
| `support-chat-conversations` (`…-conversations-65077fad`) | 24/24 | n/a | 27/27 | 27/27 | 27/27 | 27/27 | 1.19 |
| `support-chat-small-talk` (`…-small-talk-4fd5063d`) | 18/18 | 0/24 | 36/42 | 41/42 | 42/42 | 38/42 | 1.19 |

Small-talk dataset run alone with `--dataset small-talk`, with traces (`agentic-gpt-6-luna-none-k4-s3-small-talk-4fdeffb2`, 42 runs = 14 examples × 3):

| | `searched` | `skipped_search` | `sources` | `grounded` | `meets_expectation` | `search_count` |
|---|---|---|---|---|---|---|
| Baseline | 18/18 | 0/24 | 35/42 | 40/42 | 37/42 | 1.14 |

Latency and tokens per run (p50). Examples with earlier turns are listed apart: their run includes the live earlier turns, so they are not comparable with single messages.

| Group | Runs | p50 latency | p50 tokens | Mean cost reported by LangSmith |
|---|---|---|---|---|
| Small talk, single message | 15 | 3.41 s | 3957 | 0.00048 |
| Boundary, single message | 15 | 4.83 s | 4436 | 0.00060 |
| Small talk after an answer (includes the earlier turn) | 9 | 8.82 s | 13586 | 0.00135 |
| Boundary after an answer (includes the earlier turn) | 3 | 7.93 s | 13916 | 0.00142 |

Failures of the small-talk run, per example:
- `skipped_search`: all 8 small-talk examples fail 3/3 (the forced search), as expected.
- `capabilities-es`, `capabilities-en`: `sources` fails 3/3. The answer states facts about Nimbo and cites documents. `meets_expectation` fails 3/3 on `capabilities-es` and 1/3 on `capabilities-en`; `grounded` fails 1/3 on `capabilities-es`.
- `thanks-after-answer-en`: `sources` 1/3, `grounded` 1/3 and `meets_expectation` 1/3 fail.
- Boundary examples: no failure.

Of the 8 small-talk examples, only `capabilities-*` and one `thanks-after-answer-en` repetition fail quality metrics, so the "no information" risk of the prompt (Risks) did not show for greetings.

## Results

Full runs (three datasets, 3 repetitions) on 2026-11-09, `gpt-6-luna`, `k=4`, `max_searches=3`. Baseline rows are the ones under `## Baseline`.

| Dataset | Run | `searched` | `skipped_search` | `grounded` | `no_forbidden_text` | `meets_expectation` | `search_count` |
|---|---|---|---|---|---|---|---|
| answers | Baseline | 72/72 | n/a | 75/75 | 75/75 | 75/75 | 1.59 |
| answers | Iteration 0 (`…-26da3e9c`) | 72/72 | n/a | 75/75 | 75/75 | 75/75 | 1.57 |
| answers | Iteration 1 (`…-d0901026`) | 72/72 | n/a | **74/75** | 75/75 | 74/75 | 1.59 |
| conversations | Baseline | 24/24 | n/a | 27/27 | 27/27 | 27/27 | 1.19 |
| conversations | Iteration 0 (`…-conversations-2d44876e`) | 24/24 | n/a | 27/27 | 27/27 | 27/27 | 1.22 |
| conversations | Iteration 1 (`…-conversations-f1eeb09f`) | 24/24 | n/a | 27/27 | 27/27 | 27/27 | 1.15 |
| small-talk | Baseline (`…-small-talk-4fdeffb2`) | 18/18 | 0/24 | 40/42 | 42/42 | 37/42 | 1.14 |
| small-talk | Iteration 0 (`…-small-talk-753e4ee9`) | 18/18 | **23/24** | 42/42 | 42/42 | 41/42 | 0.64 |
| small-talk | Iteration 1 (`…-small-talk-f0299132`) | 18/18 | 24/24 | 42/42 | 42/42 | 41/42 | 0.60 |

Iteration 1 only adds examples ("Hola", "Gracias", "Listo, chau", and "even right after an answer") to the small-talk rule of `SYSTEM_PROMPT`.

Savings, small-talk dataset, single messages (iteration 0 against the baseline; the examples with earlier turns include those turns and are not comparable). Iteration 1 has no latency or tokens: LangSmith rate-limited the run again and lost its small-talk traces and 12 of 27 conversation runs.

| Group | p50 latency | p50 tokens | Mean cost reported by LangSmith |
|---|---|---|---|
| Small talk: baseline | 3.41 s | 3957 | 0.00048 |
| Small talk: iteration 0 | 1.45 s | 1076 | 0.00003 |
| Boundary: baseline | 4.83 s | 4436 | 0.00060 |
| Boundary: iteration 0 | 4.55 s | 4703 | 0.00044 |

Diagnosis of the failing examples:
- Iteration 0, `skipped_search`, `farewell-es` ("Listo, chau" after an answer), 1 of 3 repetitions: the model searched `despedida, chau`, then answered with a greeting. This motivated iteration 1.
- Iteration 1, `grounded` and `meets_expectation`, `mixed-partial-question-es`, 1 of 3 repetitions: searches `["costo o comisión de un retiro inmediato en Nimbo; ¿qué información tiene el centro de ayuda sobre la capital de Australia?"]`. The answer gave the NIM-020 fee and then stated "La capital de Australia es Canberra" before saying the help center has no information. This is a real leak of the model's own knowledge, the risk named in proposal.md (`agentic-rag` iteration 0). The same example passed 3/3 in the baseline and in iteration 0.
- Other failures are judge variance on single repetitions: `voseo` ("¡De nada!", "¡Listo, chau!" and one answer in each of `can-you-see-my-account-es` and `out-of-scope-capital`, where the judge's own comment says the answer is fine) and `meets_expectation` on `greeting-with-question-en` (steps given as a paragraph).

Outcome (2026-11-09): the free first turn is kept, with the iteration 1 prompt. `searched` is 100% on all three datasets and `skipped_search` is 24/24. `grounded` is 74/75 on `support-chat-answers`, below the 100% floor of proposal.md. The author decided to accept the one Canberra leak (`mixed-partial-question-es`, 1 of 3 repetitions) as run-to-run noise, against the acceptance rule that sends a missed non-negotiable to the fallback. The fallback (restoring the forced search) was therefore not applied. The leak is a real answer from the model's own knowledge, and it did not appear in the baseline or in iteration 0. If it recurs, the next change should look at it.
