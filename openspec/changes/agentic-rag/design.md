# Design

## Context

See proposal.md for the motivation. These facts about the current code shape the approach:

- `chat.py` builds a `StateGraph` with `rewrite → retrieve → generate`. Conversation state is checkpointed per `thread_id`. `messages` (with the `add_messages` reducer) holds only questions and answers, and only `generate` writes it. `documents` and `search_query` are overwritten on every run.
- `get_chat_model` (`api.py`) returns `ChatOpenAI(...).bind(response_format={"type": "json_object"})`. That is a `Runnable`, which cannot take `bind_tools`. Both nodes parse the reply with `PydanticOutputParser`, and the prompts carry its format instructions.
- Both endpoints map `OpenAIError` and `OutputParserException` to `503` or to an `error` event.
- `ask_stream()` streams the graph with `stream_mode=["messages", "values"]`. It keeps only chunks from the `generate` node and extracts the `answer` field with `parse_partial_json`.
- `tests/fakes.py` builds on `FakeListChatModel`. It returns strings only, records the messages it received, and streams one character per chunk. It does not implement `bind_tools`.
- `ChatOpenAI` here uses Chat Completions: no `reasoning`, no built-in tools, no `use_responses_api`. The LangChain OpenAI docs state that `bind_tools(tools, response_format=Schema, strict=True)` makes each reply either tool calls or schema-conforming content. OpenAI strict mode requires `parallel_tool_calls=False`.
- `run_evals.py` calls `ask()` directly with an `InMemorySaver` graph. It runs one experiment per dataset with 1 repetition.

## Goals / Non-Goals

**Goals:**
- A ReAct loop where one model call decides between searching and answering, and the final answer keeps today's `ModelAnswer` fields and post-processing (`sources` only from retrieved ids, none when coverage is `none`, `html.unescape`).
- An agent node and a tool list that a later change can extend with more tools, without restructuring the graph.
- Numbers that compare the pipeline and the agent on the same datasets.

**Non-Goals:**
- Async graph or endpoints.
- A generic tool registry, tool-execution framework or other abstractions for future tools. The search tool is executed by its own node.
- Changing the API or page contracts.

## Decisions

### 1. A hand-built loop on `StateGraph`, not LangChain's `create_agent`

```
START -> agent --(tool calls, under the limit)--> search --> agent
           |
           +--(final answer)--> END
```

The `agent` node calls the model with the system prompt, the trimmed history (`_history`, unchanged), the question and the steps of this run. When the reply has tool calls, the graph routes to `search`. When it has none, `agent` parses the final answer and writes `answer` and `messages`, as `generate` does today.

`create_agent` (in the installed `langchain` package) is rejected. It keeps tool calls and tool results in the `messages` channel, which is also the checkpointed conversation. That would break "a conversation holds only questions and answers" and the 6-exchange trimming, which counts messages. A custom loop costs about two nodes and one conditional edge.

### 2. State: the conversation and a per-run scratchpad

New `ConversationState` keys:
- `steps: list[AnyMessage]`: the `AIMessage`s with tool calls and their `ToolMessage`s.
- `documents: list[Document]`: all documents retrieved in this run, deduplicated by id.
- `searches: list[str]`: the queries, read by the evals.

None of the three has a reducer. The node that changes one of them returns the whole new list. `ask()` and `ask_stream()` pass `{"question": q, "steps": [], "documents": [], "searches": []}` as input, so a run never sees the previous run's steps, even though the checkpointer keeps them in the thread. `search_query` and `rewrite` are removed. `messages` is unchanged and still written only by the final answer.

- Alternative: an `add_messages` reducer on `steps`. It is rejected because passing `[]` does not reset a reducer channel, so a reset node would be needed.

### 3. Model binding: tool + strict structured output, bound in `chat.py`

`get_chat_model` returns the plain `ChatOpenAI(model=...)`, and `ChatContext.model` becomes a `BaseChatModel`. The `agent` node binds:

```python
model.bind_tools(
    [SearchHelpCenter],
    response_format=ModelAnswer,
    strict=True,
    parallel_tool_calls=False,
    tool_choice="none" if len(state["searches"]) >= ctx.max_searches else None,
)
```

`SearchHelpCenter` is a Pydantic schema with a single `query: str`. Its docstring tells the model when to use it. The tool is exposed as `search_help_center`. The `search` node executes it, because the tool needs `ctx.store` from the runtime context, so no Python function is bound as a tool.

The final reply is parsed with `ModelAnswer.model_validate_json(reply.text)`. A `ValidationError` is raised as `OutputParserException`, so the endpoints' existing `503` and `error` handling covers it. `PydanticOutputParser`, its format instructions and `REWRITE_PROMPT` go away.

- Alternative: `json_object` mode with format instructions, as today. It is rejected because strict `json_schema` guarantees the structure, and the docs confirm it works together with tools.
- Alternative: reading `additional_kwargs["parsed"]`. It is rejected because the fakes would have to produce it, while `reply.text` is the same for the fakes and for OpenAI.

### 4. Search limit by `tool_choice="none"`

Once `len(searches) == max_searches`, the next `agent` call is bound with `tool_choice="none"`, so the model must answer with what it has. The tool stays bound, because the history contains tool calls. If the model still returns tool calls, `agent` raises `OutputParserException` and the endpoints answer `503` or an `error` event. A loop guard on recursion depth is not needed, because each `search` visit adds at least one query.

The `search` node runs every tool call of the reply. With parallel calls off there is normally one. Each call adds one query, one `ToolMessage` and its documents, and calls beyond the limit are answered with a `ToolMessage` that says the limit was reached, because OpenAI requires a reply for every tool call id.

### 5. Search results and the prompt

Each `ToolMessage` carries the documents as today's `<document id="...">` blocks. It ends with the reminder that the current user message carries today: "Write the answer in the language of the question...". That reminder works around Spanish documents pulling answers into Spanish, so it has to stay right before the model writes. The documents appended to `documents` are deduplicated by id, and they give the `titles` map that filters `source_ids`, exactly as `generate` does today.

The system prompt keeps every current rule, rewritten from "the documents in the user message" to "the search results of the current question". It adds:
- For any question about Nimbo (products, fees, limits, policies), call `search_help_center` before answering.
- Before answering, check every part of the question against the results. For each part they do not state explicitly, search again with a query for that part. Never infer a missing fact from wording (spike finding c0).
- Search queries must be self-contained: resolve references to earlier messages.
- Questions outside the help center (greetings, general knowledge) may be answered without a search, with coverage `none`.

The question goes as a plain `HumanMessage` wrapped in `<question>` tags.

### 6. Streaming: only the final answer's JSON

`ask_stream()` keeps the `parse_partial_json` extraction, with two changes:
- It filters on `langgraph_node == "agent"` and skips chunks that carry `tool_call_chunks`.
- It resets the buffer when `metadata["langgraph_step"]` changes, because `agent` runs once per turn.

A tool-call turn has no `answer` field to extract, so nothing reaches the visitor even if the model writes text before a tool call. If OpenAI does not stream the structured content in chunks, the stream sends no `delta` and only `done`, which the spec allows. The first task's spike checks which case applies.

### 7. Fakes: scripted tool calls

In `tests/fakes.py`:
- `search_call(query)` returns a marker string, for example `json.dumps({"search": query})` under a reserved key. `RecordingFakeChatModel` turns it into `AIMessage(content="", tool_calls=[...])` from `_generate`, and into one `AIMessageChunk` with `tool_call_chunks` from `_stream`.
- `bind_tools(tools, **kwargs)` records `kwargs` in `self.bound` and returns `self`, so tests can assert `tool_choice="none"`.
- `FlakyChatModel`, `PausingChatModel` and `FailingChatModel` keep their behavior on string replies.
- `rewrite_reply` is removed.

Tests keep going through the HTTP API. Embedding calls stay observable through `CountingFakeEmbeddings.embedded_texts`, which records one entry per search.

### 8. Configuration

`app.yaml` changes:
- `retrieval.k: 4`
- new `retrieval.max_searches: 3`

`Settings` gains `max_searches`, and `ChatContext` gains `max_searches`. Both are read in `api.py` and `run_evals.py`. The eval sweep changes `app.yaml` between runs. The experiment prefix includes `k` and `max_searches`, so runs are told apart without new CLI options.

### 9. Evals: baseline first, then the agent

1. First, while `chat.py` is still the pipeline:
   - Add the compound examples to `EXAMPLES`, for instance cost + timing of an instant withdrawal (NIM-020 + NIM-013), and two to three more questions that need two documents. Each one names its expected source ids.
   - Add `num_repetitions=3` to `client.evaluate`.
   - Make the prefix `pipeline-<chat model>-k<k>`.
   - Run once. That experiment is the baseline, and it is never re-run.
2. After the agent:
   - The targets read `searches` from `graph.get_state(config).values` and return it in the outputs.
   - New evaluators: `searched` (score: at least one search, skipped for `no_information` examples), the "answered without searching" metric, and `search_count` (numeric).
   - Prefix `agentic-<chat model>-k<k>-s<max_searches>`.

Latency and tokens come from LangSmith's experiment comparison view (traced runs), so no code is needed for them.

## Risks / Trade-offs

- [Latency: at least 2 model calls per question, which is 1 more than today's first question, and searches run one at a time because parallel calls are off] → It is measured against the baseline and reported as the cost of the gain. Turning parallel calls back on is a later option, with non-strict tools.
- [Under-retrieval: the model answers a Nimbo question without searching] → The prompt rule, plus the `searched` evaluator, which turns the risk into a rate. Forcing `tool_choice="required"` on the first turn stays available if the rate is high.
- [Language drift: tool results last in the context pull answers into Spanish] → The language reminder ends every `ToolMessage`, and the judge's `correct_language` catches regressions.
- [Structured content may not stream with tools bound] → The first task's spike checks it. The fallback (only `done`) is spec-compliant, but the page would lose progressive text, which would be a reason to revisit before archiving.
- [Larger context: up to `max_searches × k` documents] → `k` goes to 4, documents are deduplicated, and the sweep picks the knee between correctness and tokens.
- [Baseline lost if run after the code changes] → Task 1 comes before any change to `chat.py`. The pipeline stays reproducible from git history.
- [Eval cost: 2 datasets × 3 repetitions × (baseline + 2–3 sweep configs)] → Only 2–3 sweep configurations, and the judge model stays `gpt-4.1-mini`.

- [Under-searching compound questions: with a minimal prompt, the spike's model did not search a second time, and it invented a missing fact] → The "check every part" prompt rule (decision 5), measured by the compound eval examples and the judge's `grounded`. If the rule is not enough, the next options are a stronger prompt or a separate check step, decided from eval numbers.

## Migration Plan

No data migration. The index is reused, because `k` only changes the query. Open conversations end on restart, as they do today. Rollback is reverting the change commits.

## Open Questions

- Final `k` and `max_searches`: picked from the sweep in task 6. It only changes `app.yaml`.

## Baseline

Task 1.2, 2026-11-06. The unchanged pipeline (`k=8`, one search per question), with 3 repetitions. Latency and tokens come from the LangSmith experiment stats of the target runs, without the judge.

| Experiment | Runs | All metrics | p50 latency | p99 latency | Tokens / run | Cost |
|---|---|---|---|---|---|---|
| `pipeline-gpt-4.1-mini-k8-aacad7da` (support-chat-answers, 19 examples) | 57 | 100% (voseo 39/39) | 3.3 s | 5.9 s | ~4,975 (4,767 prompt) | $0.079 |
| `pipeline-gpt-4.1-mini-k8-conversations-d46acec8` (support-chat-conversations, 8 examples) | 24 | 100% | 5.9 s | 8.1 s | ~10,690 (earlier turns included) | $0.082 |

Finding: the pipeline passes the 3 new compound examples in every repetition, because `k=8` puts both documents in one search's results. On these datasets the agent can at best tie on correctness. Its case is cost (fewer documents per prompt with `k=4`) against more model calls and latency. Questions that one `k=8` search cannot cover would test a correctness gain. Whether to add them is decided before task 6.2.

## Spike findings

Task 1.3, 2026-11-06. `gpt-4.1-mini` with `langchain-openai` 1.6.7, bound as in decision 3, using a minimal system prompt and one hand-written NIM-020 document.

- (a) Pass. A fee question returns one `tool_calls` entry (`SearchHelpCenter`, with the self-contained Spanish query "costo retiro inmediato a cuenta bancaria") and `content == ""`. It used 220 tokens.
- (b) Pass. After the `ToolMessage`, there are no tool calls, and `content` is `ModelAnswer` JSON that `model_validate_json` accepts. `additional_kwargs["parsed"]` holds the same object. It used 368 tokens.
- (c) Pass. With `tool_choice="none"`, the model answers with valid JSON and no tool calls.
- (c0) Finding. For "¿Cuánto cuesta un retiro inmediato y cuánto tarda?", with tools allowed and only the fee document retrieved, the model did not search again. It answered "El tiempo que tarda es inmediato" with coverage `full`, a fact inferred from the word "inmediato". This led to the "check every part" prompt rule and the risk entry above.
- (d) Pass. When streamed, the tool-call turn gives 0 content chunks and 12 `tool_call_chunks`. The final answer arrives as 74 content chunks of JSON text, so the `parse_partial_json` extraction keeps working and `delta` events stay progressive.
- Minor: Pydantic emits a `PydanticSerializationUnexpectedValue` warning when it serializes a reply whose `additional_kwargs["parsed"]` holds the `ModelAnswer`. It is only a warning, but if it floods the logs, drop `parsed` from the reply before it is traced or stored. The final reply is never stored in the state (decision 2).
