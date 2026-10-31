# Proposal

## Why

The page shows nothing but the three-dot indicator until the whole answer is generated, which takes several seconds for a long answer. Showing the answer while it is being written makes the chat feel responsive. This is the streaming change that `add-chatbot` deferred on 2026-10-14 ("a later change that adds a separate endpoint and keeps the JSON one").

## What Changes

- New endpoint `POST /api/chat/stream`. It takes the same body as `POST /api/chat` and sends the answer as server-sent events while it is generated. (Decided 2026-10-30.)
- `POST /api/chat` stays as it is. It returns the full answer as one JSON response. The API tests use it, and so does every client that wants a single response. The LangSmith evals keep calling the chat directly, not over HTTP. (Decided 2026-10-30.)
- The page asks its questions through the streaming endpoint and shows the answer text as it arrives. (Decided 2026-10-30.)
- Validation, unknown or expired conversation, and rate limit are answered with their status codes (`422`, `404`, `429`) before any event is sent. Once the stream has started, every failure is reported as an `error` event. The streaming endpoint never responds `503`. (Decided 2026-10-30.)
- The stream sends three kinds of events: `delta` (more answer text), `done` (the final answer with its sources, `conversation_id` and `expires_in_seconds`), and `error`. The answer in `done` is the authoritative one, and the page replaces the text it streamed with it. (Decided 2026-10-30.)
- Both endpoints share the same per-IP rate limit: 10 questions per minute in total. (Decided 2026-10-30.)
- The three-dot indicator stays until the first answer text arrives. The visitor cannot send another question until the answer is finished or has failed. (Decided 2026-10-30.)
- If the answer fails after part of it was shown, the page removes the partial text and shows the generic error message. The question was not answered, so it is not part of the conversation, and the page shows it the same way. (Decided 2026-10-30.)
- A question whose stream ends before `done`, for any reason (including the client disconnecting), is not answered: it does not become part of its conversation and does not change when the conversation expires. (Decided 2026-10-30.)
- Out of scope (Decided 2026-10-30):
  - Streaming the progress steps (rewriting, searching) as events.
  - Cancelling an answer from the page.
  - Resuming a stream that was cut.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `support-chat-api`:
  - New requirement: the streaming endpoint and its events.
  - Per-IP rate limit: covers both endpoints with one shared limit.
  - Upstream failure response: on the streaming endpoint it is an `error` event.
  - Unanswered questions are not part of the conversation: a stream that ends without `done` counts as unanswered.
- `support-chat-ui`:
  - Conversation display: the page uses the streaming endpoint and shows the answer while it arrives.
  - Pending state: the indicator stays until the first answer text, and sending stays blocked until the answer is finished.
  - Error messages: an `error` event, or a stream that ends without `done`, shows the generic error in place of any partial answer.

## Impact

- Backend:
  - `nimbo/chat.py`: a streaming counterpart of `ask()` that streams the graph and yields the answer text as it is generated. `ask()` keeps using `invoke`.
  - `nimbo/api.py`: the new endpoint. The conversation checks and the cleanup after a failure are shared with `POST /api/chat`, and the rate-limit middleware covers both paths.
- Dependencies: none. Server-sent events use FastAPI's `StreamingResponse`, partial JSON parsing uses `langchain_core`, and the page reads the stream with `fetch`.
- Tests: new API tests for the stream. The fake chat models also cover the streaming path, which LangChain uses when the graph is streamed. Playwright tests mock the streaming endpoint.
- Frontend: `app/chat.tsx` (stream reading, partial answer rendering).
- Evals: no change.
- Docs: the README API table gains the new endpoint.
