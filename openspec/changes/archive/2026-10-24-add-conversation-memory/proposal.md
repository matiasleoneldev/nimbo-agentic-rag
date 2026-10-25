# Proposal

## Why

Every question is answered on its own today, so a follow-up such as "¿y en Chile?" right after "¿Cuál es el mínimo por retiro inmediato?" is not understood. Visitors expect a chat to remember what was said earlier in the same window. The roadmap also points to LangGraph, and a conversation memory needs the same base (graph, checkpointer, conversation id) that the future support agent will build on.

## What Changes

- The chat remembers the conversation inside the same page: follow-up questions are understood in the context of the earlier questions and answers. Reloading the page still starts an empty, new conversation. (Decided 2026-10-24.)
- The backend creates the conversation id. The first question is sent without one, every answer returns it, and the page sends it with the next question. (Decided 2026-10-24.)
- A conversation expires after 15 minutes without an answered question. (Decided 2026-10-24.)
- The page warns the visitor 5 minutes before the conversation expires. It learns the remaining time from the API, not from a value of its own. (Decided 2026-10-24.)
- When the 15 minutes pass, the page marks the conversation as expired by itself. Earlier messages stay visible, and the next question starts a new conversation. There is no "keep the conversation" button: asking a question is what keeps it alive. (Decided 2026-10-24.)
- The warning says the conversation expires "in less than 5 minutes" ("en menos de 5 minutos"), not "in 5 minutes". It is visible from minute 10 to minute 15, so a fixed "5 minutes" would be wrong for most of that time. There is no countdown. (Decided 2026-10-24.)
- The expired notice stays visible until the next question is answered. A question that fails does not hide it. (Decided 2026-10-24.)
- If a question was still waiting for its answer when the page expired the conversation, and the API then answers it, the page shows that answer and continues the conversation with it, because the API answered it before the conversation expired. (Decided 2026-10-24.)
- A question sent with an unknown or expired conversation id is rejected with `404`, and nothing is answered. The page then shows an expiry message and drops the id. (Decided 2026-10-24.)
- A follow-up question is first rewritten into a self-contained question, and that rewritten question is the only text embedded for retrieval. The first question of a conversation is embedded as typed. (Decided 2026-10-24.)
- Only the 6 most recent exchanges of a conversation are passed to the model. The number lives in `backend/app.yaml`. (Decided 2026-10-24.)
- The conversation history holds only the questions and the answers. It never holds the retrieved documents. (Decided 2026-10-24.)
- Grounding stays per question. Earlier turns are used only to understand what the visitor is asking. Every fact in an answer comes from the documents retrieved for the current question, so `sources` always shows where each fact came from. (Decided 2026-10-24.)
- Conversations are kept in the API process memory. A restart of the API ends all open conversations, and the visitor then sees the expiry message. (Decided 2026-10-24.)
- A new LangSmith eval dataset, `support-chat-conversations`, measures multi-turn answers. It includes comparison questions that span turns, so the evidence can show whether a later change needs to carry documents across turns. (Decided 2026-10-24.)
- **BREAKING** (API behavior): questions sent in the same conversation are no longer answered independently, so a client that relied on that guarantee can get a different answer. The new fields are additive: requests may carry `conversation_id`, and the response body gains `conversation_id` and `expires_in_seconds`. A client that ignores them keeps working, and each of its questions starts a new conversation.
- Out of scope (Decided 2026-10-24):
  - The LangGraph support agent (tools, case resolution). It comes in its own change.
  - Carrying the documents cited in earlier turns into later turns.
  - One retrieval per entity named in the question.
  - Answering questions about the conversation itself ("¿qué te pregunté antes?"). Under the per-question grounding rule, such a question gets the no-information answer. This is a known limitation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `support-chat-api`:
  - Ask endpoint: carries the conversation id, and its response gains new fields.
  - Question validation: also covers the conversation id.
  - Grounding, language and sensitive data: take the conversation into account.
  - New requirements: conversations, follow-up questions, retrieval for follow-up questions, conversation expiry, and failed questions left out of the conversation.
- `support-chat-ui`:
  - Conversation display: the page continues the conversation.
  - Error messages: gain the expired-conversation case.
  - New requirements: the expiry warning and the page-side expiry.
- `corpus-ingestion`:
  - Document embeddings are computed only at ingestion: the text embedded for a follow-up question is the rewritten question.

## Impact

- Backend:
  - `nimbo/chat.py` becomes a LangGraph graph with three nodes: rewrite, retrieve and generate. It runs with an in-memory checkpointer.
  - `nimbo/api.py`: new request and response fields, a `404` response, and conversation expiry.
  - `app.yaml` and `nimbo/config.py`: new settings for the exchange limit and the conversation lifetime.
- Dependencies:
  - `langgraph` is already installed as a dependency of `langchain`. It becomes a direct dependency, because the code imports it.
  - No new package is installed.
- Tests:
  - New and updated API tests. The fake chat model answers both model calls, rewrite and generation.
  - `test_chat_requests_are_independent` is replaced.
- Frontend: `app/chat.tsx` and `app/i18n.ts` (conversation id, expiry timer, new texts). New Playwright tests use a fake clock.
- Evals: `evals/run_evals.py` gains the `support-chat-conversations` dataset and its runner. It costs OpenAI credits when run.
- Docs: the README's "no conversation memory" line and the API table.
