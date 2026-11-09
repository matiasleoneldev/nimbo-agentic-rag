# Proposal

## Why

Every message to the chat triggers a help-center search, small talk included. The `agent` node forces a search on its first turn, and the spec requires one per question. So "Hola" or "¡Gracias!" costs one search and a second model call with the retrieved documents in context. In a manual check on 2026-11-09, "hola, buen día" got a correct greeting with no sources, but it took 5 s on one try and 7.82 s on another. The forced search was added in `agentic-rag` (2026-11-06) because `gpt-4.1-mini` answered some Nimbo questions without searching (`searched` 60/63). The switch to `gpt-6-luna` (2026-11-07) kept the forced search unchanged and never measured the new model without it. Small talk behavior is also unspecified. The greeting comes out right because the model reads the situation well, not because a requirement asks for it. The prompt even pushes the other way: it says to answer that the help center does not have the information for anything the search results lack.

## What Changes

- Small talk becomes specified behavior. Small talk is a message that only greets, thanks, says goodbye, or asks in general what the chat can do, and asks nothing else. It is answered without a help-center search and with empty `sources`. A message that also asks anything else (for example "Hola, ¿cuánto cuesta un retiro inmediato?" or "Gracias, ¿y en Chile?") is not small talk and is searched. (Decided 2026-11-09.)
- An answer to "what can you do" describes the chat itself: it answers questions using Nimbo's help center and it cannot see any visitor's account. A small-talk answer never states facts about Nimbo, and it is not a no-information answer. (Decided 2026-11-09.)
- A question about the visitor's account, such as "¿Podés ver mi cuenta?", is not small talk, even though it asks what the chat can do. "No access to user accounts" already requires general information from the documents for it, so it is searched. (Decided 2026-11-09.)
- The agent decides on its own whether to search, with no new tool and no router (Decided 2026-11-09):
  - The forced search on the first turn is removed. The model chooses freely on every turn except at the search limit, where searching stays disabled.
  - A small-talk rule is added to the system prompt.
  - A `small_talk` tool would add a decision point that can fail on mixed messages and gives the model nothing it lacks. A router before the agent only pays off with high small-talk volume, and both are out of scope. If the evals show that the free first turn loses searches on Nimbo questions, a router or a revised prompt goes to a later change.
- Evals (Decided 2026-11-09):
  - A new LangSmith dataset, `support-chat-small-talk`. It holds small-talk examples (Spanish and English, alone and after an answered question) and boundary examples that must search (mixed greetings, thanks with a follow-up, and Nimbo questions that sound like "what can you do").
  - It is a separate dataset, so the totals of the existing datasets stay comparable with the 2026-11-07 results.
  - A new `skipped_search` evaluator scores the small-talk examples. `searched` keeps scoring every other example.
  - A baseline runs first on the current code, with the forced search. It gives the reference latency and tokens for small talk, and a same-day reference, since `gpt-6-luna` has no dated snapshot. Decided 2026-11-09, to save eval credits: the baseline's latency and tokens are measured on `support-chat-small-talk` only. The other two datasets keep the pass rates of the 2026-11-09 baseline run (their traces were lost to the LangSmith monthly trace limit), and their latency and tokens are not compared.
- Acceptance (Decided 2026-11-09, following the floor set by `agentic-rag` and kept by `switch-chat-model-gpt-6-luna`):
  - Non-negotiable: `grounded`, `no_forbidden_text` and `searched` stay at 100% on all three datasets. `searched` is what measures the main risk: a Nimbo question taken for small talk and answered without sources.
  - `out-of-scope-capital` must still pass `grounded` and `meets_expectation` in every repetition. Without a forced search, the model may answer it from its own knowledge, as it did in `agentic-rag` iteration 0.
  - Non-negotiable: `skipped_search` reaches 100% on the small-talk examples. The spec says small talk is never searched, so a lower rate would leave the spec describing behavior the code does not have. (Decided 2026-11-09.)
  - No other answer-quality metric may fall below the same-day baseline. As in the previous change, no margin is fixed in advance. Whether a difference of a few points is noise is the author's decision, recorded with its date in design.md.
  - Latency and tokens are reported, not gated (Decided 2026-11-09, as in the previous change). That covers p50 and tokens per run on every dataset, plus the small-talk savings, baseline against change.
  - Exception (decided 2026-11-09, after the results): the author accepted `grounded` at 74/75 on `support-chat-answers` after one prompt iteration, as noise. design.md records it under `## Results`.
  - If the rule is not met after at most one prompt iteration, the forced first search comes back. The small-talk requirement is then revised before archiving, so the spec never describes behavior the code does not have. The dataset and the evaluator stay.
- Out of scope (Decided 2026-11-09): new tools, a router or classifier, fixed template answers, API or page contract changes, and changes to the model, `k` or `max_searches`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `support-chat-api`:
  - New requirement "Small talk".
  - "Help-center searches": the at-least-one-search rule applies to every question that is not small talk.
  - "Answers are grounded in help-center documents": small-talk answers are the one exception, and they must not state facts about Nimbo.

## Impact

- `backend/nimbo/chat.py`: the `tool_choice` of the first `agent` turn and `SYSTEM_PROMPT`.
- `backend/tests/test_chat_api.py`:
  - `test_chat_first_turn_must_search` is replaced by a small-talk test.
  - The `tool_choice` assertion in `test_chat_stops_searching_at_limit` is updated.
  - The comment in `test_chat_answer_without_search_has_no_sources` is updated.
- `backend/evals/run_evals.py`: the new dataset, the `small_talk` reference flag, and the `skipped_search` evaluator.
- `README.md`: "it always searches first", the dataset list, and the results.
- No API, page, database or dependency change. The page already hides the source list when `sources` is empty.
