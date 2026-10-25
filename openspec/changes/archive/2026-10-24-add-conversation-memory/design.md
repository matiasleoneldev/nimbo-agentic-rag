# Design

## Context

- [backend/nimbo/chat.py](../../../backend/nimbo/chat.py) `answer_question()` answers one question per call in three steps:
  1. `similarity_search` on the question.
  2. One model call with `SystemMessage` plus a `HumanMessage` holding the documents and the question.
  3. JSON parsed into `ModelAnswer`.
- The model comes from the `get_chat_model` dependency, bound to JSON mode. Tests override it with `RecordingFakeChatModel`, which returns canned JSON strings in order.
- [backend/nimbo/api.py](../../../backend/nimbo/api.py):
  - `create_app()` builds one `RateLimiter` per app.
  - `chat` is a sync endpoint (FastAPI threadpool).
  - It catches `OpenAIError` and `OutputParserException` and returns `503`.
- [backend/evals/run_evals.py](../../../backend/evals/run_evals.py) calls `answer_question()` directly as its LangSmith target.
- [frontend/app/chat.tsx](../../../frontend/app/chat.tsx) keeps `entries` in React state. `isChatResponse` checks only `answer` and `sources`.
- `langgraph` 1.2.12 is already in `poetry.lock` as a dependency of `langchain` 1.4. Two APIs this design relies on are confirmed in the installed packages:
  - `InMemorySaver.delete_thread()`
  - `StateGraph(context_schema=...)`
- No `langgraph-checkpoint-postgres` is installed, and none is needed.

See proposal.md for the motivation and the dated decisions.

## Goals / Non-Goals

**Goals:**
- One linear graph (rewrite, retrieve, generate) that the future agent can extend by adding nodes, without rewriting it.
- Keep the FastAPI dependency seams (`get_chat_model`, `get_embeddings`), so the tests keep replacing OpenAI with fakes exactly as today.
- Bounded memory use: every conversation is deleted at most one request after it expires.

**Non-Goals:**
- Running more than one API worker or replica. Conversations live in one process.
- Streaming answers.
- Grouping LangSmith traces into threads.
- Summarizing old exchanges. They are dropped instead.

## Decisions

### API term: `conversation_id`, not `thread_id`

The living UI spec already speaks of "the conversation", and the spec rules ask to reuse existing terms. The public field is therefore `conversation_id`. Internally its value is passed as LangGraph's `configurable.thread_id`, so "thread" stays a LangGraph detail.

The ids are `uuid4().hex`: 32 characters, which fits the 64-character limit in the spec.

### Graph state and nodes

```
                 configurable.thread_id = conversation_id
                                |
START --> rewrite --> retrieve --> generate --> END
            |                         |
   skips the model when        appends Human(question) + AI(answer)
   messages is empty           to messages, in one update
```

The state is a `TypedDict` with these keys:
- `question`: the question as sent.
- `search_query`: the self-contained question, or `question` itself on the first turn.
- `documents`: the documents retrieved in this turn.
- `answer`: the `ChatAnswer` of this turn.
- `messages`: the history, an `Annotated[list[AnyMessage], add_messages]`.

Each node does one thing:
- **rewrite**:
  - With an empty history, it sets `search_query = question` and makes no model call.
  - Otherwise it calls the model with a rewrite prompt, the trimmed history and the question, and parses `{"search_query": str}` with a `PydanticOutputParser`. The prompt tells the model to keep the question's language and never to answer it.
  - It uses JSON because the injected model is bound to JSON mode. That way one `ChatModel` dependency serves both calls.
- **retrieve**: runs `similarity_search(search_query, k)`. This is the only embedding of the request, which keeps the corpus-ingestion requirement.
- **generate**:
  - The prompt is `SystemMessage`, then the trimmed history (plain question and answer texts), then today's `HumanMessage` with the documents and the question.
  - A new system-prompt rule says that earlier messages only explain what is being asked, and that facts must come from the documents in the last message.
  - The source filtering and the `html.unescape` step stay as they are, applied to this turn's documents.

**Why `messages` is written only by generate:** if the question entered `messages` as graph input, as in `MessagesState` examples, a question that failed with `503` would remain in the history. Here a failed run leaves `messages` untouched, and the next turn's input overwrites `question`. A new `invoke` with input starts a fresh run, not a resume.

`documents` is overwritten on every turn. It is never added to `messages`, so earlier documents never reach the model.

Alternatives rejected:
- `MessagesState` with the input appended: it pollutes the history on failures.
- Retrieving and generating in one node: it would hide the retrieval step in LangSmith traces, which is the step the conversation evals need to inspect.

### Runtime context instead of closures

The graph is compiled once in `create_app()` with an app-scoped `InMemorySaver`. The per-request values travel in a `context_schema` dataclass: the model, the `PGVectorStore`, `retrieval_k` and `max_exchanges`. These values come from the FastAPI dependencies, so `dependency_overrides` keep working, and the graph does not depend on FastAPI.

Alternative rejected: compiling a graph per request with closures. It works too, but it rebuilds the graph on every request, and the graph then cannot be reused in the evals runner.

### Trimming: by message count

Both model calls receive:

```
trim_messages(messages, strategy="last", token_counter=len,
              max_tokens=2 * max_exchanges, start_on="human")
```

`token_counter=len` counts messages, so the limit is exactly the 6 most recent exchanges. That is deterministic, which makes the "only the 6 most recent exchanges" scenario testable with the fake model. Exchanges are always complete, because generate appends the question and its answer together.

The stored state is not pruned. Expiry deletes it, and the rate limit bounds how much it can grow before that: at most 10 questions per minute per IP.

`max_exchanges: 6` and `ttl_seconds: 900` go in a new `conversations:` section of `app.yaml`, and `Settings` gains both fields.

### Conversation registry and expiry

`nimbo/conversations.py` holds a small `ConversationRegistry`, shaped like `RateLimiter`: an injectable clock, a `threading.Lock`, and a `dict[str, float]` that maps each id to the time of its last answered question.

| Operation | Behavior |
|---|---|
| `is_open(id)` | `False` if the id is unknown or expired |
| `touch(id)` | Records "answered now". Called only after a `200` |
| `sweep()` | Deletes expired ids from the dict and calls `checkpointer.delete_thread(id)` for each one |

The flow of a request in `chat`:
1. Run `sweep()`.
2. If a `conversation_id` was sent and is not open, return `404` `{"detail": "Conversation not found. Start a new conversation."}`. No model call and no embedding happen.
3. Otherwise, use the sent id, or `uuid4().hex` when none was sent.
4. Invoke the graph.
5. On success, call `touch(id)` and return `expires_in_seconds = ttl_seconds`.
6. On `503`, call neither `touch` nor anything else, so a failed first question never creates a conversation.

`sweep()` is O(open conversations) on every request. It gets a `ponytail:` comment naming the ceiling (fine for a demo's traffic) and the upgrade path (a background timer, or `PostgresSaver` with a `DELETE` job). The rate limit still counts `404`s, as the existing requirement says.

`create_app()` gains a `clock` parameter, defaulting to `time.monotonic`. The same clock goes to the registry and to the existing `RateLimiter`, so a test that moves time forward moves both. That way the API tests can move time forward through the HTTP interface, without sleeping.

Alternative rejected: storing the last-activity time inside the checkpoint and reading it back. That needs a `get_state` per request and still needs a sweep to free memory.

### Dependency: declare `langgraph` directly

Add `langgraph (>=1.2.11,<1.3.0)` to `[project].dependencies`. This is the same range `langchain` 1.4 already requires, so the lock file resolves the same 1.2.12 and nothing new is installed.

Justification: the code now imports `langgraph` directly (`StateGraph`, `InMemorySaver`), and a direct import must not rely on a transitive pin. No other dependency is added:
- `trim_messages` is in `langchain_core`.
- `InMemorySaver` is in `langgraph-checkpoint`, already installed.

`langgraph-checkpoint-postgres` and `langmem` are not added (see proposal).

### Public API of `nimbo/chat.py`

`chat.py` exports:
- `build_graph(checkpointer)`
- `ask(graph, question, conversation_id, context) -> ChatAnswer`

`answer_question()` goes away. `api.py` and `evals/run_evals.py` both call `ask()`. The single-question dataset runs each example in a new conversation, which reproduces today's behavior.

### Evals: dataset `support-chat-conversations`

- Example inputs are `{"turns": [str, ...], "question": str}`. The outputs reuse the existing fields: `language`, `expectation`, `required_source_ids`, `any_source_ids`, `no_information` and `must_not_contain`.
- The target:
  1. Compiles the graph with its own `InMemorySaver`.
  2. Creates a `uuid4` conversation.
  3. Asks every turn live.
  4. Returns the answer to `question`.
- The evaluators `sources` and `no_forbidden_text` are reused unchanged. The `judge` prompt gains an "Earlier questions" line when `turns` is present, so a follow-up like "¿y en Chile?" can be judged.
- `main()` runs both datasets, one experiment each.

Examples, each named after the spec scenario it measures:

| Example | Turns → question | Expects |
|---|---|---|
| `follow-up-country-es` | "¿Cuál es el mínimo por retiro inmediato?" → "¿y en Chile?" | 500 CLP; NIM-020 |
| `follow-up-timing-es` | "¿Cuánto cuesta un retiro inmediato?" → "¿y cuánto tarda?" | minutes; NIM-013 |
| `comparison-standard-withdrawal-es` | "¿Cuánto cuesta un retiro inmediato?" → "¿y es más caro que el retiro estándar?" | standard is free; NIM-020 |
| `comparison-business-account-es` | "¿Cuánto cuesta un retiro inmediato?" → "¿y para una Cuenta de Negocios?" | same conditions as Personal Accounts; NIM-021 (cross-document) |
| `language-switch-en-es` | English fee question → "¿y en Chile cuál es el mínimo?" | Spanish; NIM-020 |
| `card-number-earlier-turn-es` | card question → "¿y si sigue sin funcionar?" | card number absent |
| `topic-change-es` | fee question → "¿Cómo activo la verificación en dos pasos?" | NIM-004; no withdrawal content |
| `follow-up-out-of-scope-es` | fee question → "¿y cuál es la capital de Australia?" | no-information |

Every expectation is checked against the corpus PDF before it is added. The NIM-013, NIM-020 and NIM-021 expectations above were checked on 2026-10-24. NIM-021 states that business withdrawals have the same conditions as personal ones.

### Frontend

`chat.tsx` gains two pieces of state:
- `conversationId: string | null`
- `expiry: { phase: "active" | "warning" | "expired"; at: number } | null`

**When an answer arrives:**
- It stores `conversation_id`.
- It computes `at = Date.now() + expires_in_seconds * 1000` and sets the phase to `active`.
- One `useEffect` schedules two `setTimeout` calls, one at `at - 300_000` (to `warning`) and one at `at` (to `expired`). On `expired` it also sets `conversationId` to `null`.
- The effect cleans up its timers on each new answer.
- Every answered question resets `expiry` to `active`. That one rule hides both the warning and the expired notice. It also covers an answer that arrives after the page already expired the conversation: the page adopts that answer's `conversation_id`, because the server answered it before the conversation expired. A failed question does not touch `expiry`, so the expired notice stays.

**When a `404` arrives:**
- It shows an error entry with `t.expiredError`.
- It sets `conversationId` to `null` and clears `expiry`.

**What the page shows:**
- The warning or the expired notice is a `role="status"` line under the input, next to the sensitive data notice.
- `isChatResponse` also checks `conversation_id` (string) and `expires_in_seconds` (number).
- `i18n.ts` gains `expiryWarning`, `expiredNotice` and `expiredError` in both languages.

The page needs no clock synchronization with the server. Its timer starts when the response arrives, a little after the server's own timer. The few seconds in which the page still thinks the conversation is open end in the `404` path, which the spec already covers.

**E2E:**
- The tests call `page.clock.install()` before `goto`, then `page.clock.fastForward()`.
- The mocked `/api/chat` route records the request bodies, so the tests can assert whether `conversation_id` was present.

## Risks / Trade-offs

- [The API is run with more than one worker or replica, and conversations split across processes] → The README states that the API must run as a single process. A `ponytail:` comment on the checkpointer names `PostgresSaver` as the upgrade path. With LangGraph, swapping it is a one-line change in `build_graph`.
- [Restarting the API (deploy, crash, `--reload`) ends every open conversation] → Accepted on 2026-10-24. The visitor sees the expired-conversation message and asks again.
- [Memory grows with the open conversations] → Expiry deletes them within one request of expiring. The worst case is the conversations active in the last 15 minutes, each bounded by the rate limit.
- [A follow-up adds a second model call, with its latency and cost] → The first question of a conversation skips the rewrite. The rewrite prompt is short and uses the same model.
- [A bad rewrite retrieves the wrong documents] → The `support-chat-conversations` dataset measures it, follow-up and comparison cases included. A failing comparison case is the evidence for carrying documents across turns in a later change.
- [Two requests in the same conversation run at the same time, and the last write wins] → The page never sends while an answer is pending. A client that does it on purpose only damages its own conversation.
- [Background tabs throttle `setTimeout`, so the warning appears late] → Acceptable: it is informative only, and the `404` path covers any gap.
- [Sensitive data a visitor typed stays in API memory for up to 15 minutes] → It is never written to disk. The sensitive data notice on the page stays unchanged.

## Migration Plan

- There is no data migration.
- The backend and the frontend ship together:
  - An old page against the new API keeps working, because it ignores the new fields. Each of its questions starts a new conversation.
  - A new page against an old API rejects the responses (`isChatResponse`) and shows the generic error.
- Rollback: revert both together.
