# Tasks

Unless a task says otherwise, verify the backend tasks with `poetry run ruff format . ; poetry run ruff check . ; poetry run mypy . ; poetry run pytest` in `backend/`, with `docker compose up -d db` running. Tasks marked **manual** call the real OpenAI API and cost credits. The author runs them, and they never go into pytest.

## 1. Baseline and spike (before any change to `nimbo/chat.py`)

- [x] 1.1 In `backend/evals/run_evals.py`, while `chat.py` is still the pipeline (design.md, decision 9):
  - Add to `EXAMPLES` the compound example `fee-and-timing-instant-withdrawal-es` ("¿Cuánto cuesta un retiro inmediato y cuánto tarda?", required NIM-020 and NIM-013). Add two more that each need two documents, with their required source ids checked against the manifest.
  - Pass `num_repetitions=3` to `client.evaluate`.
  - Prefix experiments `pipeline-<chat model>-k<k>`.

  Verify with ruff and mypy. No pytest change is needed.
- [x] 1.2 **Manual**: run `poetry run python -m evals.run_evals` on the unchanged pipeline. Record the two experiment names and their pass rates in a `## Baseline` note at the end of design.md. Verify that both experiments appear in LangSmith with 3 repetitions.
- [x] 1.3 **Manual spike**: a throwaway script in the scratchpad, not committed. Bind `ChatOpenAI(model="gpt-4.1-mini")` exactly as in design.md, decision 3, with `SearchHelpCenter` and `ModelAnswer`. Check and record in design.md under `## Spike findings`:
  - (a) a Nimbo question returns `tool_calls` and empty content;
  - (b) after a `ToolMessage`, the reply is `ModelAnswer` JSON in `content`;
  - (c) with `tool_choice="none"` the model answers instead of calling the tool;
  - (d) when streamed, the final JSON arrives in several content chunks, and the tool-call turn arrives as `tool_call_chunks`.

  If (b) or (c) fails, stop and revise design.md before group 4.
- [x] 1.4 In `run_evals.py`, add 3 "hard" examples, each covering three topics far apart in the corpus (proposal.md, harder questions):
  - `send-abroad-limit-dispute-es`: international send fee, monthly limit, and opening a dispute. Required NIM-020, NIM-022 and NIM-041.
  - `close-account-dispute-hold-es`: closing an account with an open dispute and held money, and when that money is released. Required NIM-005 and NIM-015.
  - `verify-2fa-card-es`: verifying identity, turning on two-step verification, and requesting the card. Required NIM-002, NIM-004 and NIM-060.

  Check each expectation against the PDF text (`nimbo.pdf_text`) before writing it. Verify with ruff and mypy.
- [x] 1.5 **Manual**: re-run the baseline with the hard examples, still on the unchanged pipeline. Update `## Baseline` in design.md with the new experiment names and per-metric results, and say whether one `k=8` search covered the hard examples. Verify that the new experiments appear in LangSmith with 3 repetitions.

## 2. Configuration

- [x] 2.1 In `backend/app.yaml`, set `retrieval.k: 4` and add `retrieval.max_searches: 3` with a comment. Add `max_searches` to `Settings` (`nimbo/config.py`). Extend `tests/test_config.py` to assert `max_searches == 3`. Verify with pytest.

## 3. Fake model with scripted tool calls

- [x] 3.1 In `backend/tests/fakes.py` (design.md, decision 7):
  - Add `search_call(query)`.
  - Make `RecordingFakeChatModel` turn its marker into an `AIMessage` with one tool call, from both `_generate` and `_stream` (as `tool_call_chunks` when streamed).
  - Add `bind_tools` that records its kwargs in `bound` and returns `self`.
  - Keep string replies, `FAIL` and `PAUSE` behaving as they do today.

  Verify with mypy, and through group 4's tests.

## 4. Agent graph

Each scenario below traces to the named test in `backend/tests/test_chat_api.py`, or to a LangSmith eval dataset example.

- [x] 4.1 Rewrite the graph in `backend/nimbo/chat.py` (design.md, decisions 1–5):
  - Add the `agent` and `search` nodes and a conditional edge.
  - Add the `steps`, `documents` and `searches` state keys without reducers, reset by the input of `ask()` and `ask_stream()`.
  - Add the `SearchHelpCenter` schema and the binding with `strict`, `parallel_tool_calls=False` and `tool_choice="none"` at the limit.
  - Parse the final answer with `ModelAnswer.model_validate_json` → `OutputParserException`.
  - Each `ToolMessage` ends with the language reminder.
  - Update the system prompt with the search rules.
  - Remove `rewrite`, `retrieve`, `generate`, `REWRITE_PROMPT` and both `PydanticOutputParser`s.

  In `nimbo/api.py`, `get_chat_model` returns the unbound `ChatOpenAI`, and `ChatContext` gets `max_searches`; update `evals/run_evals.py` accordingly. Update the module docstring.
- [x] 4.2 Move every scripted sequence in `test_chat_api.py` from `rewrite_reply` to `search_call`, and remove `rewrite_reply`. Replace `test_chat_embeds_only_question` and `test_chat_follow_up_embeds_only_search_query` with `test_chat_embeds_each_search_query`: two searches embed exactly their two queries. Verify that the whole suite passes.
- [x] 4.3 Help-center searches:
  - Referential follow-up retrieves the right document → eval `follow-up-timing-es` (support-chat-conversations)
  - Question that needs two documents → eval `fee-and-timing-instant-withdrawal-es` (support-chat-answers)
  - Documents of every search are retrieved for the question → `test_chat_sources_from_every_search`
  - Search limit → `test_chat_stops_searching_at_limit` (the fake asks for 4 searches. Assert 3 embedded queries, a final bind with `tool_choice="none"`, and a `200` answer.)
  - Answer without a search has no sources → `test_chat_answer_without_search_has_no_sources`
  - Also add `test_chat_returns_503_when_model_searches_past_limit`: the model returns a tool call after `tool_choice="none"` (design.md, decision 4).
- [x] 4.4 Answers are grounded in help-center documents:
  - Fee question answered from the fee document → eval `fee-instant-withdrawal-es`
  - Comparison across turns → eval `comparison-standard-withdrawal-es`
  - Question about Nimbo is searched → eval evaluator `searched` (task 6.1)
- [x] 4.5 Follow-up questions use the conversation:
  - Follow-up understood from the conversation → eval `follow-up-country-es`
  - Only the 6 most recent exchanges are used → `test_chat_uses_only_six_most_recent_exchanges` (updated to the new message layout)
  - Searches are not part of the conversation → `test_chat_conversation_holds_no_searches` (the follow-up's model input holds the earlier question and answer, and neither the earlier query nor any `<document`)

## 5. Streaming

- [x] 5.1 Update `ask_stream()` (design.md, decision 6): filter on `langgraph_node == "agent"`, skip chunks with `tool_call_chunks`, and reset the buffer on a new `langgraph_step`. If spike (d) showed no content chunks, record in design.md that only `done` carries the answer, and raise it with the author before archiving.
- [x] 5.2 Streamed answer events:
  - Only the answer text is streamed → `test_chat_stream_streams_only_answer_text` (updated: a question with a `search_call`, asserting that no `delta` contains its query)
  - Deltas carry the answer as it is written, Done event carries sources and conversation data, and Same answer rules on both endpoints keep `test_chat_stream_deltas_join_to_answer`, `test_chat_stream_done_carries_sources_and_conversation` and `test_chat_stream_drops_unretrieved_source_ids`, run with a search before the answer.
  - Verify that every existing `test_chat_stream_*` test passes.

## 6. Agent evals and sweep

- [x] 6.1 In `run_evals.py` (design.md, decision 9):
  - The targets read `searches` from `graph.get_state(...)` and return it in the outputs.
  - Add the `searched` evaluator (skipped for `no_information` examples) and the numeric `search_count`.
  - Prefix `agentic-<chat model>-k<k>-s<max_searches>`.

  Verify with ruff and mypy.
- [x] 6.2 **Manual**: run the evals with `k=4, max_searches=3`, then with 1–2 more configurations (for example `k=8, max_searches=3` and `k=4, max_searches=2`). Add a `## Results` table to design.md comparing each configuration with the baseline: pass rate per metric, `searched` rate, mean `search_count`, p50 latency and mean tokens (from LangSmith's comparison view). Set `app.yaml` to the chosen configuration and state why it was chosen.
- [x] 6.3 Apply the acceptance rule (design.md, decision 10):
  - If `searched` < 100%, force `tool_choice="required"` on the first turn, add `test_chat_first_turn_must_search`, and re-run 6.2.
  - If no configuration matches the baseline on every metric, iterate the prompt and re-run, at most twice.
  - Record the outcome (accepted configuration, or the change stopped before archive) in design.md under `## Results`.

## 7. Docs and roadmap

- [x] 7.1 Rewrite the Roadmap paragraph of `openspec/config.yaml`: the chatbot is an agent with tools (since 2026-11-06, change `agentic-rag`), its only tool is the help-center search, and every new tool or support-agent capability needs its own proposal. Keep the rule against abstractions built in advance. Verify with `openspec validate agentic-rag`.
- [x] 7.2 Update `README.md` (architecture section and the eval instructions, including the baseline/agentic prefixes) and `CLAUDE.md` (the `chat.py` line, which now reads "agent loop with a help-center search tool"). Verify that the commands in the README still match.
