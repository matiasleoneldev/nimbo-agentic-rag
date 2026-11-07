# Design

## Context

- `get_chat_model` (`nimbo/api.py`) returns `ChatOpenAI(model=settings.chat_model)`. The `agent` node (`nimbo/chat.py`) binds `SearchHelpCenter` with `response_format=ModelAnswer`, `strict=True`, `parallel_tool_calls=False`, and a `tool_choice` of `"required"` on the first turn, `"none"` at the search limit, and the default otherwise. `ask_stream` reads the final answer from the streamed JSON content chunks and skips chunks that carry `tool_call_chunks`.
- `gpt-6-luna` is a reasoning model. Its default effort is `medium`, and the levels are `none`, `low`, `medium`, `high`, `xhigh` and `max`. On Chat Completions it supports function calling only with `reasoning_effort` set to `none` (OpenAI model docs, read 2026-11-07). Its docs list structured outputs and streaming, but do not say whether strict JSON schema, `parallel_tool_calls` or `tool_choice` work alongside tools.
- `langchain-openai` 1.6.7 (already locked) accepts a standard `reasoning_effort` parameter. Its docs say `ChatOpenAI` routes to the Responses API automatically when the `reasoning` parameter is set, and that `reasoning_effort` translates to `reasoning.effort`. So it is unclear whether `reasoning_effort` alone moves the calls to the Responses API.
- The floor and the "known defects" come from the `agentic-rag` archive (design.md, Results; proposal.md, Acceptance revision).

## Goals / Non-Goals

**Goals:**
- Run the agent on `gpt-6-luna` without reasoning, with no change to `chat.py` or the prompt.
- Measure it against `gpt-4.1-mini` on the same extended datasets, with the same judge and 3 repetitions.

**Non-Goals:**
- Making the model configurable per request, or supporting several models at once.
- Testing the OpenAI wiring in pytest: tests override `get_chat_model` with fakes and never call OpenAI.

## Decisions

1. **An optional `models.chat_reasoning_effort` in `app.yaml`, set to `none`.** `Settings` gets `chat_reasoning_effort: str | None`, which is `None` when the key is absent. `gpt-4.1-mini` rejects `reasoning_effort`, so the value must be optional, and switching back means removing the key and changing `models.chat`. Alternative considered: hardcode `reasoning_effort="none"` in `get_chat_model`. That would break the rollback, and it hides a model-specific value in code.

2. **`get_chat_model` passes `reasoning_effort` and pins Chat Completions with `use_responses_api=False`.** Without the pin, `reasoning_effort` might send the calls to the Responses API, where the model's function calling, streaming chunks and reasoning items are unverified (proposal.md, deferred). The pin also keeps `gpt-4.1-mini` on the API it uses today. `reasoning_effort=None` is `ChatOpenAI`'s default, so a single constructor call serves both models, with no branch. Alternative considered: the Responses API with `reasoning_effort="none"`. It is deferred together with reasoning.

3. **A spike before any code change** (tasks.md, group 1). It is a throwaway script in the scratchpad, never committed, using one hand-written NIM-020 document, as in `agentic-rag` task 1.3. It binds `ChatOpenAI(model="gpt-6-luna", reasoning_effort="none", use_responses_api=False)` exactly as the `agent` node does. Checks:
   - (a) A fee question returns one `SearchHelpCenter` tool call with a self-contained query, and empty content.
   - (b) After the `ToolMessage`, the reply has no tool calls and its content is `ModelAnswer` JSON that `model_validate_json` accepts.
   - (c) With `tool_choice="none"`, the model answers with valid JSON and no tool calls.
   - (d) When streamed, the tool-call turn arrives as `tool_call_chunks`, and the final answer arrives as several content chunks of JSON text that `parse_partial_json` reads progressively.
   - (e) The request goes to `/v1/chat/completions` with `reasoning_effort: "none"`. Check the LangSmith trace's invocation parameters, or the `openai` client's debug log.
   - (f) For "¿Cuánto cuesta un retiro inmediato y cuánto tarda?", with only the fee document returned, check whether the model searches again or infers the timing. This is the `agentic-rag` (c0) case. It is informative, not a gate.

   If (a) to (e) fail, stop and revise proposal.md and this design before group 2. Record the token counts and anything unexpected, such as a temperature or schema warning.

4. **A new `gpt-4.1-mini` baseline on the extended datasets.** The new examples change the totals, so the `agentic-rag` floor (62/66, 63/66) cannot be compared directly. The baseline runs with the code unchanged except for the new examples and the prefix. The two experiments then differ only in `models` in `app.yaml`.

5. **The experiment prefix includes the effort when one is set:** `agentic-<chat model>[-<effort>]-k<k>-s<max_searches>`, for example `agentic-gpt-4.1-mini-k4-s3` and `agentic-gpt-6-luna-none-k4-s3`. The effort is also added to the experiment metadata (`models.chat_reasoning_effort`). This keeps a later reasoning run distinguishable in LangSmith.

6. **New eval examples.** Each expectation is checked against the PDF text (`nimbo.pdf_text`) before it is written, and the required ids against `manifest.json`. Each one measures an existing requirement:
   - `fee-timing-2fa-card-es`, four topics: "¿Cuánto cuesta un retiro inmediato, cuánto tarda, cómo activo la verificación en dos pasos y cómo pido la Tarjeta Nimbo?" Required NIM-020, NIM-013, NIM-004 and NIM-060. With `max_searches=3`, one search per topic is impossible, so the model must combine topics in a query or rely on `k=4`. A failure here measures search planning, not a bug. Requirements: "Help-center searches" and "Partially covered questions".
   - `2fa-and-account-recovery-en`: the English version of `2fa-and-account-recovery-es`. Required NIM-004 and NIM-003. Language failures followed Spanish queries. Requirement: "Answer language follows the question".
   - `withdrawal-minimum-two-countries-and-timing-es`: "¿Cuál es el mínimo por retiro inmediato en Chile y en México, y cuánto tarda?" Expected 500 CLP and 10 MXN, each labeled, and the timing. Required NIM-020 and NIM-013. Requirement: "Variants by country and account type".
   - Conversations, `compound-follow-up-es`: the turn is "¿Cuánto cuesta un retiro inmediato?", then "¿y cuánto tarda y cómo activo la verificación en dos pasos?" Required NIM-013 and NIM-004. Requirements: "Follow-up questions use the conversation" and "Help-center searches".

## Risks / Trade-offs

- [`gpt-6-luna` without reasoning may be no better at search planning than `gpt-4.1-mini`, since the reasoning that would plan sub-queries is off] → That is exactly what the change measures. The acceptance rule sends the next change to reasoning or question splitting.
- [Strict structured output, `tool_choice` or `parallel_tool_calls` may be rejected alongside tools on this model] → Spike checks (b) and (c) catch it before any code change.
- [`langchain-openai` may treat an unknown `gpt-6-*` name as a reasoning model, and drop or warn about parameters such as temperature] → `agent` sets no temperature. Spike check (e) shows the parameters actually sent.
- [Noise: 3 repetitions over about 25 examples. A difference of 1 or 2 points may be chance] → No margin is fixed (proposal.md, Acceptance). `## Results` reports the per-example failures of both runs, so the author can tell a systematic difference from a one-off, and the author records the decision.
- [`gpt-6-luna` has no dated snapshot, so OpenAI may change the model behind the same id] → The results are tied to the date they were run. `## Results` records that date, and a later regression would show up when the evals are re-run.
- [Both models are likely to fail `sources` on the four-topic example] → It is deliberate. It counts in both runs, so it does not bias the comparison, and the per-example failures are reported.
- [Latency may change, and output tokens are cheaper but may be more numerous] → p50 latency and tokens per run are reported next to the pass rates, as in `agentic-rag`.

## Migration Plan

Rollback is configuration only: set `models.chat: gpt-4.1-mini` and remove `models.chat_reasoning_effort`. Nothing is stored per model: no re-ingestion, and conversations live in memory.

## Spike findings

Task 1.1, 2026-11-07. `ChatOpenAI(model="gpt-6-luna", reasoning_effort="none", use_responses_api=False)` with `langchain-openai` 1.6.7, bound as in the `agent` node, with the real `SYSTEM_PROMPT` and one hand-written NIM-020 document.

- (a) Pass. With `tool_choice="required"`, a fee question returns one `search_help_center` call with a self-contained Spanish query ("¿Cuánto cuesta un retiro inmediato a mi cuenta bancaria? comisión o tarifa exacta por país") and empty content. It used 914 input and 36 output tokens.
- (b) Pass. After the `ToolMessage`, there are no tool calls, and the content is `ModelAnswer` JSON that `model_validate_json` accepts: the fee and every country minimum, coverage `full`, sources `["NIM-020"]`. It used 1,070 input and 82 output tokens.
- (c) Pass. With `tool_choice="none"`, valid `ModelAnswer` JSON and no tool calls.
- (d) Pass. When streamed, the tool-call turn gives 40 `tool_call_chunks` and 0 content chunks. In the final turn, `parse_partial_json` saw the `answer` grow 51 times, from 0 to 154 characters, so `delta` events stay progressive.
- (e) Pass. `_use_responses_api` is `False`, and the request payload has `reasoning_effort: "none"`, no `reasoning` key, `tool_choice`, `parallel_tool_calls: false`, `tools` and the strict `response_format`. OpenAI accepted every call. Reasoning tokens were 0 on every call.
- (f) Improvement. For "¿Cuánto cuesta un retiro inmediato y cuánto tarda?", the first query covered both parts. With only the fee document returned, the model searched again for the timing ("cuánto tarda en acreditarse un retiro inmediato…") instead of inferring it. `gpt-4.1-mini` answered without that second search in the `agentic-rag` spike (c0).
- Minor:
  - `question_language` was "es" in one reply and "Spanish" in another. It is not used outside the model, so it is harmless.
  - Pydantic emits the same `PydanticSerializationUnexpectedValue` warning for `parsed` that the `agentic-rag` spike recorded.
  - OpenAI reported cache writes (`cache_creation`) on repeated prompts.

## Baseline

Task 2.3, 2026-11-07. `gpt-4.1-mini`, `text-embedding-3-large`, `k=4`, `max_searches=3`, 3 repetitions, on the extended datasets (25 answer examples, 9 conversation examples). Pass rates are as `run_evals` prints them, summed over the 3 repetitions. Latency and tokens are the median and mean over the root target runs (the judge is not included).

- `agentic-gpt-4.1-mini-k4-s3-843f1d58` (answers):
  - sources 64/76, meets_expectation 70/74.
  - grounded 74/74, correct_language 74/74, plain_text 74/74, voseo 53/53, no_forbidden_text 75/75, searched 72/72.
  - search_count 1.24, p50 3.3 s, ~5,627 tokens per run.
- `agentic-gpt-4.1-mini-k4-s3-conversations-eb609594` (conversations):
  - sources 25/28, meets_expectation 25/26, voseo 25/26.
  - Every other metric 100%.
  - search_count 1.00, p50 5.8 s, ~9,182 tokens per run.
- Target errors, 1 run per dataset (`out-of-scope-capital`, `follow-up-out-of-scope-es`): the model returned two JSON objects one after the other ("trailing characters at line 2"). `ModelAnswer` validation failed, which the API would answer with `503`. This defect predates this change. Its run shows up as the extra `sources` failure, the `judge: 0/1` line, and totals of 74 or 76 instead of 75.
- Failures by example, out of 3 runs:
  - `sources`: `fee-timing-2fa-card-es` 2, `verify-2fa-card-es` 2, `card-request-and-declined-payment-es` 2, `withdrawal-minimum-all-countries-es` 2, `fee-and-timing-instant-withdrawal-es` 1, `withdrawal-minimum-two-countries-and-timing-es` 1, `follow-up-country-es` 1.
  - `meets_expectation`: `fee-and-timing-instant-withdrawal-es`, `withdrawal-minimum-all-countries-es`, `withdrawal-minimum-two-countries-and-timing-es`, `declined-payment-my-account-es`, `follow-up-country-es`, 1 each.
- Searches:
  - The `agentic-rag` pattern is still there: one narrow query about the first topic. `verify-2fa-card-es` got one search in 2 of 3 runs, and `card-request-and-declined-payment-es` in 2 of 3. The minimums got queries such as "mínimo retiro inmediato", which retrieve NIM-013 but not NIM-020.
  - On the four-topic example, the model searched three times, combining fee and timing in one query. It missed NIM-020 in 2 of 3 runs.

## Results

Tasks 3.2 and 3.3, run on 2026-11-07. `gpt-6-luna` has no dated snapshot, so these numbers belong to that date. Both runs use the same datasets, `k=4`, `max_searches=3`, the same judge (`gpt-4.1-mini`) and 3 repetitions. They follow the Baseline conventions.

| Run | Answers: sources / grounded / language / meets / no_forbidden / voseo | searched | search_count | p50 | Tokens / run | Conversations | search_count | p50 | Tokens / run |
|---|---|---|---|---|---|---|---|---|---|
| Baseline `agentic-gpt-4.1-mini-k4-s3-843f1d58` / `-conversations-eb609594` | 64/76 / 74/74 / 74/74 / 70/74 / 75/75 / 53/53 | 72/72 | 1.24 | 3.3 s | ~5,627 | sources 25/28, meets 25/26, voseo 25/26, others 100% | 1.00 | 5.8 s | ~9,182 |
| `agentic-gpt-6-luna-none-k4-s3-0d51344a` / `-conversations-bbcc7ebb` | 74/75 / 75/75 / 75/75 / 74/75 / 75/75 / 54/54 | 72/72 | 1.51 | 4.5 s | ~7,036 | 100% (27/27 on every metric) | 1.26 | 7.5 s | ~12,478 |

Diagnosis, from the `searches` outputs in LangSmith:
- Queries changed shape:
  - `gpt-6-luna` writes long queries that cover every part of the question ("Cómo verificar identidad en Nimbo, activar verificación en dos pasos y obtener la Tarjeta Nimbo: requisitos y pasos"). `gpt-4.1-mini` wrote a narrow query about the first topic.
  - With `k=4`, one such query usually retrieves every document a two- or three-topic question needs. This is the effect the pipeline baseline got from embedding the whole question with `k=8`.
- More follow-up searches:
  - When the results describe an exact value only in general terms, the model searches again. The second query often names the referenced document id ("NIM-020 comisión retiro inmediato mínimo por país…"), which NIM-013 points to.
  - `search_count` rose from 1.24 to 1.51 on answers, and from 1.00 to 1.26 on conversations. This is how the minimum examples got NIM-020: `withdrawal-minimum-all-countries-es` passed 3/3, against 1/3 on the baseline.
- Four-topic example (`fee-timing-2fa-card-es`): the first query combined all four topics, and a second query fetched NIM-020. All four documents were cited in 3/3 runs, against 1/3 on the baseline, with two or three searches. The search limit was never the bottleneck.
- Only remaining failure: `withdrawal-minimum-two-countries-and-timing-es`, 1 of 3. NIM-020 was retrieved but not cited, and the answer said the help center has no minimums for Chile and México. That is grounded, but wrong.
- No target errors. The baseline's duplicated-JSON error did not occur.
- Costs:
  - Tokens per run rose about 25% on answers and 36% on conversations. These are longer queries, more searches, and more retrieved documents in the prompt.
  - p50 latency rose by 1.2 s on answers (3.3 → 4.5 s) and by 1.7 s on conversations (5.8 → 7.5 s).
  - Price per token is lower: `gpt-6-luna` costs $0.10 / $0.50 per 1M input / output tokens (OpenAI model docs, 2026-11-07). `gpt-4.1-mini`'s list price is higher; it was not re-checked in this change. So the extra tokens should still cost less per question, but this change did not measure cost per question.

Outcome (2026-11-07): **`gpt-6-luna` with `reasoning_effort: none` is accepted.**
- No metric falls below the baseline. `grounded`, `no_forbidden_text` and `searched` are at 100% on both datasets.
- `sources` (74/75 vs 64/76) and `meets_expectation` (74/75 vs 70/74) are higher by margins well beyond noise. Every conversation metric is at 100%.
- The latency loss is accepted and reported, as the proposal states.
- The `agentic-rag` known defects (narrow first-topic searches; `follow-up-country-es`) did not occur in these runs.
