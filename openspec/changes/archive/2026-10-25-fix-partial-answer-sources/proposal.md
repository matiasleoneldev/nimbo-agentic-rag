# Proposal

## Why

A question that the help center covers only in part, such as "¿Cuánto cuesta un retiro inmediato y cuál es la capital de Australia?", sometimes comes back with an empty `sources` list. The answer itself is right: it gives the NIM-020 fee and says the help center has no information about the other part. The cause is the model's yes/no "has information" flag, which empties `sources` when it is false. A partly answered question does not fit a yes/no question, so the model sets the flag to false about 2 times in 5 (measured 2026-10-24 on the `mixed-partial-question-es` eval). The response then breaks the "Partially covered questions" requirement, and the page shows a fee without the document it comes from. The flakiness was accepted on 2026-10-24 on condition that a later change fixes it. This is that change.

## What Changes

- The model no longer answers a yes/no "has information" question. It states how much of the question the documents cover: all of it, part of it, or none of it. It states this before it lists the documents it used. (Decided 2026-10-25.)
- `sources` is emptied only when the model states that the documents cover none of the question. When they cover part of it, `sources` keeps the documents used for that part. (Decided 2026-10-25.)
- A three-way coverage is chosen over a renamed yes/no flag, even though the API treats "all" and "part" the same way. The three-way choice gives partial answers a value of their own, which is the clearest option for the model. One approach is tried per change, so that the eval result can be attributed to it. (Decided 2026-10-25.)
- The "no-information answer has no sources" rule now explicitly covers only answers where none of the question is covered. A partial answer is not a no-information answer.
- No change to the API contract: request and response bodies stay the same.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `support-chat-api`:
  - No-information answer: the rule that empties `sources` applies only when the documents cover none of the question.
  - Partially covered questions: gains a deterministic scenario. A partial answer keeps the sources it cites.

## Impact

- Backend: `nimbo/chat.py` changes the model output schema, the system prompt and the rule that empties sources.
- Tests: `tests/fakes.py` (`model_reply` takes a coverage value instead of the flag), the updated no-information test and a new partial-answer test in `tests/test_chat_api.py`.
- Evals: no dataset change. `mixed-partial-question-es` and `out-of-scope-capital` are re-run to measure the fix. This costs OpenAI credits.
- Docs: the README note that lists `mixed-partial-question-es` as a known flaky example.
- Dependencies: none.
