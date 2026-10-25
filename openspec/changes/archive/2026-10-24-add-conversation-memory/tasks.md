# Tasks

## 1. Setup

- [x] 1.1 Add `langgraph (>=1.2.11,<1.3.0)` to `[project].dependencies` in `backend/pyproject.toml` and run `poetry-2.2.1 lock`. Verify that `poetry.lock` still resolves `langgraph` 1.2.12 and adds no new package (`git diff backend/poetry.lock` shows only the content hash and the new direct entry).
- [x] 1.2 Add a `conversations:` section to `backend/app.yaml` (`max_exchanges: 6`, `ttl_seconds: 900`) and the matching `Settings` fields in `nimbo/config.py`. Verify with an assertion in `backend/tests/test_config.py` that both values load, and with `poetry run mypy .`.

## 2. Conversation graph and API

Each scenario below traces to the named test in `backend/tests/test_chat_api.py`. Unless a task says otherwise, verify with `poetry run ruff format . ; poetry run ruff check . ; poetry run mypy . ; poetry run pytest`, with `docker compose up -d db` running.

- [x] 2.1 Add `rewrite_reply(search_query)` to `backend/tests/fakes.py`. It returns the JSON the rewrite step expects, so a `RecordingFakeChatModel` can answer the rewrite call and the generation call in order.
- [x] 2.2 Rewrite `nimbo/chat.py` as described in design.md:
  - Add the state, the `rewrite`, `retrieve` and `generate` nodes, the runtime context, and trimming with `token_counter=len` and `max_tokens=2 * max_exchanges`.
  - Add `build_graph(checkpointer)` and `ask(...)`.
  - Add the rewrite prompt, and a grounding rule in the system prompt saying that earlier messages only explain the question.
  - Remove `answer_question`.

  Verify that the existing API tests still pass once 2.3 is done.
- [x] 2.3 Add `nimbo/conversations.py` (`ConversationRegistry`: `is_open`, `touch`, `sweep`, injectable clock, lock, and a `ponytail:` comment on the O(n) sweep). Then update `nimbo/api.py`:
  - `conversation_id` in the request (optional, at most 64 characters) and in the response, plus `expires_in_seconds`.
  - The `404` response.
  - Compile the graph once per app, with an `InMemorySaver` carrying a `ponytail:` comment about a single process and `PostgresSaver` as the upgrade.
  - A `clock` parameter on `create_app()`.
  - `touch` only after a `200`.
- [x] 2.4 Ask endpoint / Successful answer → update `test_chat_returns_answer_and_sources` so it also asserts a string `conversation_id` and an integer `expires_in_seconds`.
- [x] 2.5 Ask endpoint / Requests are independent → update `test_chat_requests_are_independent`. The second question is sent without `conversation_id`, the model receives no history, and no rewrite call happens.
- [x] 2.6 Question validation / Non-string conversation id → `test_chat_rejects_non_string_conversation_id`. Too long conversation id → `test_chat_rejects_conversation_id_over_64_chars`.
- [x] 2.7 Conversations:
  - First question starts a conversation → `test_chat_first_question_starts_conversation`
  - Follow-up continues the conversation → `test_chat_follow_up_keeps_conversation_id`
  - New conversations get different ids → `test_chat_new_conversations_get_different_ids`
- [x] 2.8 Follow-up questions use the conversation / Only the 6 most recent exchanges are used → `test_chat_uses_only_six_most_recent_exchanges`. After 7 exchanges, the 8th generation call contains the questions of exchanges 2 to 7 and not the first question.
- [x] 2.9 Conversation expiry, with the injected clock:
  - Remaining time is reported → `test_chat_reports_expires_in_seconds`
  - Expired conversation → `test_chat_expired_conversation_returns_404` (no model call, no embedding)
  - Unknown conversation → `test_chat_unknown_conversation_returns_404`
  - Activity keeps the conversation open → `test_chat_activity_keeps_conversation_open`
- [x] 2.10 Unanswered questions are not part of the conversation:
  - Failed follow-up is left out → `test_chat_failed_question_is_not_in_conversation`. A model fails once, then answers, and the next generation call does not contain the failed question.
  - Failed question does not extend the conversation → `test_chat_failed_question_does_not_extend_conversation`
- [x] 2.11 Sources list the documents the answer used / Sources of earlier answers are not carried over → `test_chat_does_not_carry_sources_from_earlier_answers`.
- [x] 2.12 corpus-ingestion:
  - Chat request embeds only the question → keep `test_chat_embeds_only_question` (first question of a conversation).
  - Follow-up embeds only the self-contained question → `test_chat_follow_up_embeds_only_search_query`. The embedded text is exactly the fake rewrite's `search_query`.

## 3. Evals

- [x] 3.1 In `backend/evals/run_evals.py`:
  - Switch the `support-chat-answers` target to `ask()`, with a new conversation per example.
  - Add the `support-chat-conversations` dataset with the eight examples in design.md: inputs `turns` and `question`, a target that asks every turn live in one conversation, and the judge prompt extended with the earlier questions.
  - Make `main()` run both datasets.

  Verify with `poetry run ruff check .` and `poetry run mypy .`.
- [x] 3.2 Run `poetry run python -m evals.run_evals` (costs OpenAI credits; ask the user first). Verify:
  - every `support-chat-answers` example still passes, so there is no regression from the graph;
  - the `support-chat-conversations` examples that trace to spec scenarios pass: `follow-up-country-es` (Follow-up understood from the conversation), `follow-up-timing-es` (Referential follow-up retrieves the right document), `comparison-standard-withdrawal-es` (Comparison across turns), `language-switch-en-es` (Language changes within a conversation) and `card-number-earlier-turn-es` (Card number in an earlier question).

  Report the results of `comparison-business-account-es`, `topic-change-es` and `follow-up-out-of-scope-es` to the user without blocking: they are the evidence for a later change.

  Result 2026-10-24: `support-chat-conversations` 8/8 on every metric. `support-chat-answers` passed everything except `sources` on `mixed-partial-question-es` (15/16). That failure is pre-existing flakiness, not a regression: asked 5 times, both the graph and the previous `chat.py` returned empty `sources` 2 times out of 5 (the model sets `has_information=false` when half the question is unanswerable). Accepted by the user on 2026-10-24, to be addressed in a later change.

## 4. Frontend

Each scenario traces to the named test in `frontend/e2e/chat.spec.ts`. Verify with `npm run lint ; npm run typecheck ; npm run test:e2e`.

- [x] 4.1 Add `expiryWarning`, `expiredNotice` and `expiredError` to `Dictionary` and both dictionaries in `frontend/app/i18n.ts`, with the texts of the spec delta. Verify with `npm run typecheck`.
- [x] 4.2 Update `frontend/app/chat.tsx`:
  - The `conversationId` and `expiry` state.
  - `isChatResponse` checks the new fields.
  - The request sends `conversation_id` when one is set.
  - The warning and expiry timers.
  - The `404` handling.
  - The status line under the input.

  Update the shared `/api/chat` mock in `chat.spec.ts` to return `conversation_id` and `expires_in_seconds`, and verify that all existing E2E tests pass.
- [x] 4.3 Conversation display:
  - Follow-up continues the conversation → `"sends conversation id with follow-up questions"`
  - Reload starts a new conversation → `"starts a new conversation after reload"`
- [x] 4.4 Expiry warning, using `page.clock`:
  - Warning after 10 idle minutes → `"shows expiry warning after 10 idle minutes"`
  - No warning before → `"does not show expiry warning before 10 minutes"`
  - New answer hides the warning → `"hides expiry warning after a new answer"`
  - English expiry warning → `"shows English expiry warning"`
- [x] 4.5 Conversation expires on the page:
  - Conversation expires after 15 idle minutes → `"expires conversation after 15 idle minutes"`
  - English expired notice → `"shows English expired notice"`
- [x] 4.6 Expired notice lasts until the next answer:
  - Expired notice hides after the next answer → `"hides expired notice after the next answer"`
  - Expired notice stays after a failed question → `"keeps expired notice after a failed question"`
- [x] 4.7 Answer that arrives after the page expired the conversation / Pending answer arrives after page expiry → `"keeps the conversation when a pending answer arrives after page expiry"`. The test delays the mocked answer past `page.clock.fastForward("15:00")`, then checks that the next request carries that answer's `conversation_id`.
- [x] 4.8 Error messages:
  - Conversation not found → `"shows expired message on 404 and starts a new conversation"`
  - English error messages → extend `"shows English error messages"` with a third response, `404`

The scenarios that are not changed keep tracing to their existing tests.

## 5. Docs and integration check

- [x] 5.1 Update [README.md](../../../README.md) and verify that it states each of these:
  - The request and response fields.
  - The `404` row in the API table.
  - Conversation memory, replacing "no conversation memory": 6 exchanges, 15 minutes, lost on reload or API restart.
  - The API must run as a single process.
  - The new eval dataset, with its example count.
- [x] 5.2 Run the full gates (backend: ruff, mypy, pytest; frontend: lint, typecheck, test:e2e). Then run the API and the page locally and check by hand that "¿Cuál es el mínimo por retiro inmediato?" followed by "¿y en Chile?" answers with the Chile minimum, and that reloading the page starts a new conversation.
