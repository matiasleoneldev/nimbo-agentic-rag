# Proposal

## Why

The chat answers through a fixed pipeline (rewrite, retrieve, generate). Every question gets exactly one search, even when it needs two documents (a cost and a timing) or none. Turning the chatbot into an agent lets the model choose whether to search, how many times and with which query. It is also the first step of the roadmap: the support agent of later changes is this same agent with more tools. The decision has to be defended with numbers, so the change measures the current pipeline and the agent on the same LangSmith datasets.

## What Changes

- The chatbot becomes an agent (ReAct loop). The model has one tool, `search_help_center(query)`. On each turn it either asks for a search or writes the final answer. The same model call that decides the searches writes the answer. (Decided 2026-11-06.)
- A question gets at most a configured number of searches (`retrieval.max_searches`, 3 to start). Once it is reached, the model must answer with the documents it already has. (Decided 2026-11-06.)
- Each search returns `retrieval.k` documents, lowered from 8 to 4 to start, because one question can now run several searches. The final values come from an eval sweep of 2 to 3 configurations in this change. (Decided 2026-11-06.)
- **BREAKING (behavior)**: The separate rewrite step is removed. The agent writes its own self-contained search queries from the conversation and the question. The first question of a conversation is no longer searched exactly as sent. (Decided 2026-11-06.)
- The documents retrieved for a question are those of all its searches, without duplicates. `sources` may only contain those. A question answered with no search has no retrieved documents, so its `sources` is empty. (Decided 2026-11-06.)
- The searches, their queries and their results never become part of the conversation. A conversation still holds only questions and answers. (Decided 2026-11-06.)
- Under-retrieval risk accepted: the model is not forced to search. It is mitigated in this change with a prompt rule (search before answering any question about Nimbo) and a new eval that counts the questions about Nimbo answered without a search. (Decided 2026-11-06.)
- The model's final answer uses OpenAI structured outputs (`json_schema`, strict) together with the tool. Parallel tool calls are turned off, because strict mode requires it. This replaces the `json_object` mode and the format instructions in the prompt. (Decided 2026-11-06, verified in the LangChain OpenAI docs.)
- The streamed `delta` events carry only the final answer text, never a search request or its query. (Decided 2026-11-06.)
- `openspec/config.yaml` roadmap: the chatbot is now an agent with tools, and today its only tool is the help-center search. Every new tool (account lookups, case actions) still needs its own proposal. (Decided 2026-11-06.)
- Evals: before any code change, a baseline experiment of the current pipeline runs on the same datasets the agent will use, which gain compound questions that need more than one document. Both run with 3 repetitions. They are compared on correctness, sources, latency, tokens, and searches per question. (Decided 2026-11-06.)
- The datasets also gain harder questions that one search is unlikely to cover: three topics far apart in the corpus. They are added while the code is still the pipeline, and the baseline is re-run with them. (Decided 2026-11-06, after the first baseline passed every compound question with `k=8`.)
- Acceptance (Decided 2026-11-06):
  - The final configuration is the one with the fewest tokens per question among those where no metric falls below the baseline.
  - `searched` must be 100% across all repetitions. If it is not, the first turn is forced to search (`tool_choice="required"`).
  - If no configuration matches the baseline, the prompt is revised and the evals re-run, at most twice. If it still does not match, the change is not merged. A latency loss is accepted and reported; a correctness loss is not.
- Out of scope (Decided 2026-11-06):
  - Any tool other than the search.
  - Showing searches as progress events in the stream or in the page.
  - Parallel searches in one model turn.
  - API or page contract changes: the request and response bodies stay the same.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `support-chat-api`:
  - Answers are grounded in help-center documents: the retrieved documents are those of all the question's searches, and a question about Nimbo is answered from at least one search.
  - Retrieval for follow-up questions: removed, and replaced by a new requirement about help-center searches (agent-chosen queries, at most the configured number of searches).
  - Follow-up questions use the conversation: a conversation holds neither the documents nor the searches.
  - Streamed answer events: no `delta` contains a search query.

## Impact

- Backend:
  - `nimbo/chat.py`: the graph becomes `agent` ⇄ `search`, plus the final answer. The `rewrite` node, its prompt and the `PydanticOutputParser`s are removed. `ask()` and `ask_stream()` keep their signatures.
  - `nimbo/api.py`: `get_chat_model` returns the unbound `ChatOpenAI`, and `chat.py` binds the tool and the response format.
  - `nimbo/config.py` and `app.yaml`: `retrieval.max_searches` is new, and `retrieval.k` goes to 4.
- Dependencies: none. The loop uses LangGraph's `StateGraph`, which is already in use, not LangChain's `create_agent` (design.md).
- Tests: the fake chat model can script tool calls. Every scripted sequence that used `rewrite_reply` moves to scripted searches. There are new tests for the search limit, for sources across two searches, and for the conversation not holding searches.
- Evals: `run_evals.py` gets compound examples, repetitions, a searches-per-question metric and an "answered without searching" evaluator.
- Frontend: no change.
- Docs: README architecture section, and `openspec/config.yaml` roadmap paragraph.
