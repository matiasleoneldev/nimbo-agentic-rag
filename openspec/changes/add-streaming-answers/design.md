# Design

## Context

See proposal.md for the motivation. These facts about the current code shape the approach:

- `generate` asks the model for a JSON object (`question_language`, `answer`, `coverage`, `source_ids`, in that order, with `json_object` mode). It parses that object, keeps only retrieved source ids, and applies `html.unescape` to the answer. The visitor reads only `answer`.
- `rewrite` calls the same chat model as `generate`. Its output is JSON too, and the visitor must never see it.
- `generate` is the only node that writes `messages`, and it writes them only after the whole answer is parsed. A run that stops before `generate` returns leaves the conversation untouched.
- `POST /api/chat` is a sync endpoint. It runs `sweep()`, checks the conversation (`404`), and calls `ask()` (`graph.invoke`). On a failure it deletes the thread of a new conversation and returns `503`. It calls `touch()` only on success.
- The rate-limit middleware matches the path `/api/chat` exactly.
- The fake chat models in `tests/fakes.py` override `_call` only. While a graph is streamed, LangChain calls the model's `_stream` instead, even when the node calls `.invoke()`, and `FakeListChatModel._stream` does not go through `_call`.
- Playwright intercepts `**/api/chat` with `route.fulfill`, which sends the whole body at once.

## Goals / Non-Goals

**Goals:**
- Stream only the `answer` text of `generate`, using the same graph, prompts and parsing as `POST /api/chat`, so both endpoints end in the same answer.
- Keep `ask()` (invoke) as it is for `POST /api/chat` and the evals.

**Non-Goals:**
- Async endpoints or an async graph. The sync graph and sync endpoints stay.
- Changing the prompt or the model's output format to make streaming easier.

## Decisions

### 1. Stream the graph with `messages` and `values` modes; filter tokens to `generate`

`ask_stream()` in `chat.py` calls `graph.stream(input, config, context=..., stream_mode=["messages", "values"])`. It yields each new piece of answer text (`str`), and finally the `ChatAnswer` built from the last `values` state. That is the same `result["answer"]` that `ask()` reads. A `messages` chunk is used only when `metadata["langgraph_node"] == "generate"`, so the rewrite tokens never reach the visitor.

LangGraph emits `messages` events even when the node calls `model.invoke()` (confirmed in the LangGraph streaming docs), so the nodes do not change.

- Alternative: call `model.stream()` inside `generate` and push text out with `stream_mode="custom"`. It is rejected because it changes a node for a transport concern, and `messages` mode already does this.
- Alternative: a separate chain outside the graph for streaming. It is rejected because it would duplicate the graph, and the two endpoints could drift apart.

### 2. Extract the answer text with `parse_partial_json`

`ask_stream()` accumulates the `generate` tokens into a buffer and calls `langchain_core.utils.json.parse_partial_json(buffer)` on each one. When the result has a string `answer` that extends the text already sent, it yields only the new suffix. When the result does not extend it (for example, a half-received escape), it yields nothing and waits for the next token. Because `question_language` comes first, the first `delta` arrives a few tokens late, which is acceptable.

The deltas carry the raw model text, without `html.unescape`. An entity split across tokens would otherwise make the text non-append-only. The `done` answer is unescaped, and the page replaces the streamed text with it (spec: "Streamed answer events").

- Alternative: `JsonOutputParser` in streaming mode. It emits whole partial objects per chunk, and we would still have to compute the diff of `answer`. The plain function is enough.
- Alternative: ask the model for plain text first and metadata after a separator. It is rejected because it changes the prompt and the parsing that the evals measure.

### 3. Server-sent events over a sync `StreamingResponse`

`POST /api/chat/stream` runs the same pre-checks as `POST /api/chat` before it returns a `StreamingResponse(media_type="text/event-stream")` over a sync generator. Starlette iterates a sync generator in its threadpool. Each event is `event: <name>\ndata: <json>\n\n`. A three-line helper builds it, and no SSE library is added.

The pre-checks are body validation (FastAPI, `422`), `sweep()` and the conversation check (`404`). Rate limiting stays in the middleware, which now matches both paths.

Inside the generator:
- Each `str` becomes a `delta` event.
- The final `ChatAnswer` leads to `touch()` and then a `done` event.
- `OpenAIError` or `OutputParserException` is logged and becomes an `error` event with the same `UNAVAILABLE` text.
- A `finally` block deletes the thread of a new conversation when `done` was not sent. That covers errors and client disconnects.

### 4. Share the endpoint logic as plain functions, not a class

The pieces both endpoints use become closures inside `create_app`, next to the endpoints:
- open-or-404: `sweep()`, then either a new id or a `404` response.
- the `ChatContext` construction.
- the failure cleanup: delete the thread of a new conversation.

`POST /api/chat` keeps its behavior and its tests.

### 5. Fakes cover the streaming path

`RecordingFakeChatModel`, `FlakyChatModel` and `FailingChatModel` also override `_stream`. They record the messages and raise `OpenAIError` where `_call` does, then delegate to `FakeListChatModel._stream`, which yields one character per chunk. That gives many `delta` events with no extra code. A mid-answer failure uses a fake that yields part of its reply and then raises `OpenAIError`.

### 6. Page reads the stream with `fetch` and a small SSE parser

`EventSource` cannot send a POST, so `askQuestion` sends `fetch(POST /api/chat/stream)`.
- `429` and `404` are handled as today.
- On `200`, it reads `response.body.getReader()` through a `TextDecoder` (`stream: true`), splits the text on blank lines, and reads the `event:` and `data:` lines.
- `delta` updates the entry through a callback, using a new `"streaming"` status that holds the partial text.
- `done` (validated with the existing `isChatResponse`) makes the entry `answered`.
- `error`, an invalid `done`, or the end of the body without `done` make it `error`, with the generic message.

The `pending` flag that blocks sending also covers `"streaming"`. The partial answer element has `aria-busy="true"`.

No package is added. Next.js does not need to proxy the stream, because the page calls the API origin directly, as it does today.

### 7. E2E tests send SSE bodies; partial states use a local streaming server

Most tests only need complete answers. `mockChat` intercepts `**/api/chat/stream`, and `reply(200, …)` fulfills with an SSE body that holds one `delta` with the whole answer and then `done`. Statuses `404`, `429` and `503` stay plain JSON responses.

Tests that must see a state in the middle of a stream (partial text, busy, error after partial, no send while streaming) cannot use `route.fulfill`, because it sends the body at once. Those tests:
1. Start a `node:http` server inside the test file. It writes the events when the test tells it to, and it sends the CORS headers.
2. Redirect the request to that server with `route.continue({ url })`.

That keeps the tests at the UI boundary without mocking `fetch` in the page.

## Risks / Trade-offs

- [The client disconnects while `generate` runs. During `messages` streaming, LangGraph may run the node in a background thread that finishes even after the generator is closed, and the node's writes could become part of the conversation.] → In LangGraph, the loop applies a node's writes to the state after the step, and the closed generator never gets there. An API test closes the stream after the first `delta` and checks that the next follow-up is generated without that question. If the test shows the writes are applied anyway, the endpoint must restore the conversation before reporting the task done.
- [The joined deltas differ from the `done` answer (HTML entities).] → `done` is authoritative by spec, and the page replaces the text. The difference is rare and lasts only until `done`.
- [Proxies or a future host buffer `text/event-stream`.] → No deployment target is set yet. The response sends `Cache-Control: no-cache`, and buffering is revisited when a host is chosen.
- [A sync generator holds a threadpool thread for the whole answer.] → This is the same cost as today's sync endpoint, which holds a thread for the whole answer too.
- [Evals measure `invoke`, and the page uses `stream`.] → Both run the same graph and the same parsing. An API test checks that `done` on the stream matches the `200` body of `POST /api/chat` for the same fake model reply.
