# Tasks

Unless a task says otherwise, verify the backend tasks with `poetry run ruff format . ; poetry run ruff check . ; poetry run mypy . ; poetry run pytest` in `backend/`, with `docker compose up -d db` running. Verify the frontend tasks with `npm run lint ; npm run typecheck ; npm run test:e2e` in `frontend/`.

## 1. Streaming the graph

- [ ] 1.1 In `backend/tests/fakes.py`, make `RecordingFakeChatModel`, `FlakyChatModel` and `FailingChatModel` also override `_stream` (design.md, decision 5). They must record the messages and raise `OpenAIError` exactly as `_call` does. Add a fake that streams the first part of its reply and then raises `OpenAIError`. Verify that the existing suite still passes unchanged.
- [ ] 1.2 Add `ask_stream(graph, question, conversation_id, context)` to `nimbo/chat.py` (design.md, decisions 1 and 2):
  - `graph.stream` with `stream_mode=["messages", "values"]`.
  - Tokens filtered to `langgraph_node == "generate"`.
  - The `answer` suffix extracted with `parse_partial_json`, yielding only append-only text.
  - A final `ChatAnswer` read from the last state.

  `ask()` stays unchanged. Verify through the API tests in group 2, with mypy strict passing.

## 2. Streaming endpoint

Each scenario below traces to the named test in `backend/tests/test_chat_api.py`.

- [ ] 2.1 In `nimbo/api.py`, move the conversation open-or-404 step, the `ChatContext` construction and the new-conversation cleanup into closures inside `create_app`, which `POST /api/chat` then uses (design.md, decision 4). Verify that the existing `POST /api/chat` tests pass unchanged.
- [ ] 2.2 Add `POST /api/chat/stream` (design.md, decision 3):
  - Pre-checks before the `StreamingResponse`.
  - `delta`, `done` and `error` events, with a helper that formats the events.
  - `touch()` only before `done`.
  - A `finally` block that deletes the thread of a new conversation when `done` was not sent.
  - `Cache-Control: no-cache`.

  Make the rate-limit middleware match both paths. In the tests, add a helper that reads a streamed response into a list of `(event, data)` pairs.
- [ ] 2.3 Streaming ask endpoint:
  - Streamed answer → `test_chat_stream_returns_deltas_then_done`
  - Invalid question on the stream → `test_chat_stream_rejects_blank_question`
  - Unknown conversation on the stream → `test_chat_stream_unknown_conversation_returns_404`
  - Follow-up on the stream continues the conversation → `test_chat_stream_follow_up_continues_conversation`
- [ ] 2.4 Streamed answer events:
  - Deltas carry the answer as it is written → `test_chat_stream_deltas_join_to_answer`
  - Done event carries sources and conversation data → `test_chat_stream_done_carries_sources_and_conversation`
  - Only the answer text is streamed → `test_chat_stream_streams_only_answer_text` (a follow-up, so the rewrite call happens too)
  - Same answer rules on both endpoints → `test_chat_stream_drops_unretrieved_source_ids`
  - Also add `test_chat_stream_done_matches_json_answer`: the same fake reply gives the same `answer` and `sources` on both endpoints, including an answer with an HTML entity (design.md, Risks).
- [ ] 2.5 Per-IP rate limit:
  - Both endpoints share the limit → `test_chat_rate_limit_is_shared_by_both_endpoints`
  - The existing scenarios keep their tests.
- [ ] 2.6 Upstream failure response:
  - Model provider unavailable on the stream → `test_chat_stream_ends_with_error_when_model_fails` (also asserts that no `done` event is sent and that `detail` is the generic message)
  - Model fails in the middle of a streamed answer → `test_chat_stream_ends_with_error_after_partial_answer`
  - Model provider unavailable keeps `test_chat_returns_503_when_model_fails`.
- [ ] 2.7 Unanswered questions are not part of the conversation:
  - Failed streamed follow-up is left out → `test_chat_stream_failed_question_is_not_in_conversation`
  - Failed first streamed question leaves no conversation → `test_chat_stream_failed_first_question_leaves_no_conversation`
  - Add `test_chat_stream_disconnect_leaves_question_out`: close the stream after the first `delta`, then send a follow-up and check that it is generated without the cut question and that the expiry did not move (design.md, Risks). If it fails, fix the endpoint before you mark this task done.
  - The existing `POST /api/chat` scenarios keep their tests.
- [ ] 2.8 In `README.md`, add `POST /api/chat/stream` to the API table with its events, and note that the page uses it and the evals call `ask()`. Verify that the documented `curl -N` example streams events against a running API.

## 3. Page reads the stream

Each scenario below traces to the named test in `frontend/e2e/chat.spec.ts`.

- [ ] 3.1 Update `app/chat.tsx` (design.md, decision 6):
  - `askQuestion` posts to `/api/chat/stream` and parses the SSE events.
  - New `"streaming"` entry status, with a delta callback.
  - `done` validated with `isChatResponse`.
  - `error`, an invalid `done`, or the end of the body without `done` give the generic error.
  - Sending blocked while the answer is pending or streaming.
  - `aria-busy` on the partial answer.

  No new package. Verify with `npm run lint ; npm run typecheck`.
- [ ] 3.2 Update the E2E helpers (design.md, decision 7):
  - `mockChat` intercepts `**/api/chat/stream`.
  - `reply(200, …)` fulfills with an SSE body (one `delta`, then `done`).
  - `holdChat` releases an SSE body.
  - Add a streaming helper that starts a `node:http` server inside the test file and redirects the request to it with `route.continue({ url })`. The test sends each event when it chooses.

  Verify that every existing E2E test passes with the new helpers.
- [ ] 3.3 Conversation display:
  - Answer appears while it is written → `shows answer text while it streams`
  - Done answer replaces the streamed text → `replaces streamed text with the final answer`
  - The other scenarios keep their tests.
- [ ] 3.4 Pending state:
  - Indicator replaced by the answer → `replaces the indicator with the first answer text`
  - Partial answer is busy → `marks the partial answer busy until done`
  - No send while the answer is being written → `does not send while the answer is being written`
  - The other scenarios keep their tests.
- [ ] 3.5 Error messages:
  - Error after part of the answer → `shows generic error after a partial answer`
  - Stream ends without an answer → `shows generic error when the stream ends without an answer`
  - The other scenarios keep their tests.
  - Answer that arrives after the page expired the conversation keeps `keeps the conversation when a pending answer arrives after page expiry`, now answered with a `done` event.

## 4. Integration check

- [ ] 4.1 With the real API (`uvicorn`, real OpenAI, which costs a few credits) and `npm run dev`, ask one suggested question. Check that the text appears progressively, that the sources appear only at the end, and that a follow-up in the same conversation works. Then run `openspec validate add-streaming-answers --strict`.
