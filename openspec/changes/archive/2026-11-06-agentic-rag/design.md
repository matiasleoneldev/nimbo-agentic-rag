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
- Never answer from the model's own knowledge, even general knowledge unrelated to Nimbo: for anything the search results do not contain, say that the help center does not have that information. This line replaced "questions outside the help center may be answered without a search" in prompt iteration 1 (see Results), and the first turn always searches (decision 10).

The question goes as a plain `HumanMessage` wrapped in `<question>` tags.

### 6. Streaming: only the final answer's JSON

`ask_stream()` keeps the `parse_partial_json` extraction, with two changes:
- It filters on `langgraph_node == "agent"` and skips chunks that carry `tool_call_chunks`.
- It resets the buffer when `metadata["langgraph_step"]` changes, because `agent` runs once per turn.

A tool-call turn has no `answer` field to extract, so nothing reaches the visitor even if the model writes text before a tool call. If OpenAI does not stream the structured content in chunks, the stream sends no `delta` and only `done`, which the spec allows. The first task's spike checks which case applies.

### 7. Fakes: scripted tool calls

In `tests/fakes.py`:
- `search_call(query)` returns a marker string, for example `json.dumps({"search": query})` under a reserved key. `RecordingFakeChatModel` turns it into `AIMessage(content="", tool_calls=[...])` from `_generate`, and into one `AIMessageChunk` with `tool_call_chunks` from `_stream`.
- `search_call` takes one or more queries (`search_call(*queries)`), all asked in one turn. Two in one reply is how the search-limit test asks for a 4th search before the limit bind, so the beyond-limit `ToolMessage` path runs (implementation note, 2026-11-06).
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

### 10. Acceptance rule for the sweep

The decision rules are in proposal.md (Acceptance). How they are applied:
- "No metric below the baseline" compares the pass rate of each metric on both datasets. The baseline is 100% on every metric, so any failed run is a regression.
- When `searched` is below 100%, the fix is `tool_choice="required"` on the first `agent` call only (`len(searches) == 0`), and the sweep is re-run. Later turns stay free, so the agent still decides whether to search again. That changes decision 4's binding, and it needs one more test (`test_chat_first_turn_must_search`, which checks the first bind's `tool_choice`).
- A prompt iteration changes only `SYSTEM_PROMPT` and the `SearchHelpCenter` docstring, and each iteration is recorded in the Results table. After two iterations without a match, the outcome is recorded in design.md and the change stops before archive.
- Revised 2026-11-06 (proposal.md, Acceptance revision): after two iterations without a match, the iteration 1 configuration is accepted with its measured loss as the floor for the next change. `grounded`, `no_forbidden_text` and `searched` are the metrics that may never fall below 100%.

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

Tasks 1.2 and 1.5, 2026-11-06. The unchanged pipeline (`k=8`, one search per question), with 3 repetitions. Latency and tokens come from the LangSmith experiment stats of the target runs, without the judge. The 1.5 run is the baseline that every agent experiment is compared against.

| Experiment | Runs | All metrics | p50 latency | p99 latency | Tokens / run | Cost |
|---|---|---|---|---|---|---|
| 1.2 `pipeline-gpt-4.1-mini-k8-aacad7da` (answers, 19 examples) | 57 | 100% | 3.3 s | 5.9 s | ~4,975 | $0.079 |
| 1.2 `pipeline-gpt-4.1-mini-k8-conversations-d46acec8` (conversations, 8 examples) | 24 | 100% | 5.9 s | 8.1 s | ~10,690 | $0.082 |
| **1.5 `pipeline-gpt-4.1-mini-k8-cc251f72`** (answers, 22 examples incl. 3 hard) | 66 | 100% (voseo 48/48) | 2.9 s | 5.4 s | ~5,020 (4,787 prompt) | $0.094 |
| **1.5 `pipeline-gpt-4.1-mini-k8-conversations-3dd6b789`** (conversations, 8 examples) | 24 | 100% | 5.5 s | 6.0 s | ~10,640 (earlier turns included) | $0.080 |

Findings:
- The pipeline passes every compound and hard example in every repetition. One `k=8` search covers even the three-topic questions.
- The reason is the corpus size. With 25 documents, `k=8` puts a third of the corpus into every prompt, so retrieval almost cannot miss. On this corpus the agent can at best tie on correctness.
- The agent's case is therefore cost: fewer documents per prompt with `k=4`, against more model calls and more latency. The sweep (task 6.2) measures exactly that, and the acceptance rule (decision 10) still requires no regression on correctness.
- A larger corpus would let retrieval precision matter. That is out of scope here, but it is the honest condition under which the agent's correctness advantage would show.

## Spike findings

Task 1.3, 2026-11-06. `gpt-4.1-mini` with `langchain-openai` 1.6.7, bound as in decision 3, using a minimal system prompt and one hand-written NIM-020 document.

- (a) Pass. A fee question returns one `tool_calls` entry (`SearchHelpCenter`, with the self-contained Spanish query "costo retiro inmediato a cuenta bancaria") and `content == ""`. It used 220 tokens.
- (b) Pass. After the `ToolMessage`, there are no tool calls, and `content` is `ModelAnswer` JSON that `model_validate_json` accepts. `additional_kwargs["parsed"]` holds the same object. It used 368 tokens.
- (c) Pass. With `tool_choice="none"`, the model answers with valid JSON and no tool calls.
- (c0) Finding. For "¿Cuánto cuesta un retiro inmediato y cuánto tarda?", with tools allowed and only the fee document retrieved, the model did not search again. It answered "El tiempo que tarda es inmediato" with coverage `full`, a fact inferred from the word "inmediato". This led to the "check every part" prompt rule and the risk entry above.
- (d) Pass. When streamed, the tool-call turn gives 0 content chunks and 12 `tool_call_chunks`. The final answer arrives as 74 content chunks of JSON text, so the `parse_partial_json` extraction keeps working and `delta` events stay progressive.
- Minor: Pydantic emits a `PydanticSerializationUnexpectedValue` warning when it serializes a reply whose `additional_kwargs["parsed"]` holds the `ModelAnswer`. It is only a warning, but if it floods the logs, drop `parsed` from the reply before it is traced or stored. The final reply is never stored in the state (decision 2).

## Results

Tasks 6.2 and 6.3, 2026-11-06. `gpt-4.1-mini`, `text-embedding-3-large`, 3 repetitions. The baseline is the 1.5 pipeline run, at 100% on every metric. Latency and tokens come from the root target runs (the judge is not included), as in the Baseline section. Pass rates are summed over the 3 repetitions. A total of 67 or 65 instead of 66 means that one judge call failed in that run.

| Run | Change from the previous row | Answers: sources / grounded / language / meets / no_forbidden | searched | search_count | p50 | Tokens / run | Conversations (all metrics) | p50 | Tokens / run |
|---|---|---|---|---|---|---|---|---|---|
| Baseline `pipeline-…-k8-cc251f72` / `-conversations-3dd6b789` | n/a | 66 / 66 / 66 / 66 / 66 of 66 | n/a | 1 | 2.9 s | ~5,020 | 100% | 5.5 s | ~10,640 |
| it0 `agentic-…-k4-s3-bac492c0` / `-conversations-18a5edd3` | Agent as designed | 56 / 64 / 66 / 56 / 66 | 60/63 | 1.11 | 3.5 s | ~4,716 | sources 21/24, searched 20/21, grounded 23/24, meets 22/24 | 5.9 s | ~7,200 |
| it1 `agentic-…-k4-s3-831488e0` / `-conversations-d08d6daa` | `tool_choice="required"` on the first turn (the `searched` rule), plus prompt iteration 1 | 62 / 66 / 65 / 63 / 66 | 63/63 | 1.15 | 3.5 s | ~4,955 | sources 22/24, others 100% | 6.2 s | ~8,377 |
| it1 `agentic-…-k8-s3-7c73acc4` / `-conversations-78bba3aa` | Same code, `k=8` | 60 / 66 / 65 / 64 / 65 | 63/63 | 1.05 | 3.7 s | ~6,482 | 100% | 6.4 s | ~12,345 |
| it2 `agentic-…-k4-s3-7328e227` / `-conversations-7e086d0f` | Prompt iteration 2 | 58/67 / 65/65 / 61/65 / 57/65 / 65 | 63/63 | 1.21 | 3.8 s | ~5,464 | 100% | 6.7 s | ~8,823 |

Prompt iterations (each changes only `SYSTEM_PROMPT` and the `SearchHelpCenter` docstring):
- Iteration 1:
  - Out-of-scope questions: the line "may be answered without a search" made the model answer "Canberra". It became "never answer from your own knowledge".
  - A new rule: search again when the results describe an exact value (an amount, a minimum, a time) only in general terms.
- Iteration 2:
  - "Count the topics and search once per topic."
  - Never put sensitive values in a search query.
  - `question_language` is never the language of the queries or of the documents.
  - Reverted, because it made the answers worse.

Diagnosis (from the `searches` outputs in LangSmith):
- The failing examples are the multi-topic ones (`verify-2fa-card-es`, `fee-and-timing-instant-withdrawal-es`, `card-request-and-declined-payment-es`, `send-abroad-limit-dispute-es`) and the minimums (`withdrawal-minimum-*`).
- The agent writes one narrow query about the first topic, for example "cómo verifico mi identidad", and stops. The baseline embedded the whole question, and with `k=8` on 25 documents that covers every topic.
- `k=8` did not fix it (60/66 sources), so the loss comes from the query, not from `k`.
- The language failures (`money-on-hold-en`, `2fa-steps-en`) follow Spanish queries.
- Asking for one search per topic (iteration 2) raised `search_count` only to 1.21, and the extra rules hurt language and minimums.

Outcome (decision 10):
- No configuration matches the baseline on every metric after two prompt iterations. Under the original rule the change would stop before archive.
- The author accepted the measured loss instead (proposal.md, Acceptance revision, 2026-11-06), so the change is **accepted with iteration 1, `k=4, max_searches=3`**:
  - It has the best answers-dataset results among the agent runs.
  - It costs about the same tokens as the baseline on single questions (~4,955 vs ~5,020) and ~21% fewer on conversations (~8,377 vs ~10,640).
  - p50 latency is about 0.6 s higher.
  - `grounded`, `no_forbidden_text` and `searched` are at 100% on both datasets.
- The code keeps the forced first search and the iteration 1 prompt.
- The floor for the next change is iteration 1's pass rates. That change tries a stronger chat model first, then a question-splitting step. A larger corpus, where one `k=8` search no longer covers the question, stays an option for showing the agent's advantage.
