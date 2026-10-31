# Spec Delta

## ADDED Requirements

### Requirement: Streaming ask endpoint
The system SHALL expose `POST /api/chat/stream`, accepting the same JSON body as `POST /api/chat`, with the same question validation, conversations, conversation expiry and authentication rules. When it accepts the question, it SHALL respond `200` with `Content-Type: text/event-stream` and send the answer as server-sent events while it is generated, as defined by the streamed answer events requirement.

#### Scenario: Streamed answer
- **WHEN** an unauthenticated client sends `{"question": "¿Cuánto cuesta un retiro inmediato?"}` to `POST /api/chat/stream`
- **THEN** the response is `200` with `Content-Type: text/event-stream`, at least one `delta` event and then one `done` event

#### Scenario: Invalid question on the stream
- **WHEN** a client sends `{"question": "   "}` to `POST /api/chat/stream`
- **THEN** the response is `422` and no event is sent

#### Scenario: Unknown conversation on the stream
- **WHEN** a client sends a question with a `conversation_id` the system never returned to `POST /api/chat/stream`
- **THEN** the response is `404` with a JSON body `{"detail": string}`, no event is sent, and no answer is generated

#### Scenario: Follow-up on the stream continues the conversation
- **WHEN** a client sends a question to `POST /api/chat/stream` with the `conversation_id` of the `done` event of its previous answer
- **THEN** the `done` event carries the same `conversation_id`, and the answer takes the earlier exchange into account

### Requirement: Streamed answer events
Each event SHALL carry a JSON object in its `data` field. Zero or more `delta` events (`{"text": string}`) MUST come first; their texts, in order, are the answer written so far. The stream MUST end with exactly one `done` or `error` event. `done` carries the body `POST /api/chat` returns on `200`, and its `answer` is authoritative: it MAY differ from the joined `delta` texts.

#### Scenario: Deltas carry the answer as it is written
- **WHEN** the answer "Te cobramos 1,5%." is generated for a question sent to `POST /api/chat/stream`
- **THEN** the `delta` texts, joined in order, read "Te cobramos 1,5%." and are followed by a `done` event whose `answer` is "Te cobramos 1,5%."

#### Scenario: Done event carries sources and conversation data
- **WHEN** a streamed answer is based on NIM-020
- **THEN** the `done` event contains the `answer`, `sources` with `{"id": "NIM-020", "title": "<NIM-020 manifest title>"}`, a `conversation_id` and `expires_in_seconds` `900`

#### Scenario: Only the answer text is streamed
- **WHEN** a follow-up question is sent to `POST /api/chat/stream`
- **THEN** no `delta` text contains the rewritten question, the question language, the coverage or any source id

#### Scenario: Same answer rules on both endpoints
- **WHEN** the generated answer cites an id that was not among the documents retrieved for the question, sent to `POST /api/chat/stream`
- **THEN** that id does not appear in the `done` event `sources`

## MODIFIED Requirements

### Requirement: Per-IP rate limit
The system SHALL accept at most 10 requests to `POST /api/chat` and `POST /api/chat/stream`, counted together, per client IP address in any 60-second window. Further requests in that window MUST be rejected with `429` and a `Retry-After` header (seconds), without generating an answer. Every request that is not rejected with `429` counts toward the limit, including requests rejected with `422`; `429` responses do not extend the window.

#### Scenario: Eleventh request in a minute is rejected
- **WHEN** a client IP sends 11 requests within 60 seconds
- **THEN** the first 10 are processed and the 11th receives `429` with a `Retry-After` header

#### Scenario: Both endpoints share the limit
- **WHEN** a client IP sends 5 requests to `POST /api/chat` and then 6 to `POST /api/chat/stream` within 60 seconds
- **THEN** the 11th request receives `429` with a `Retry-After` header and no event is sent

#### Scenario: Limit is per IP
- **WHEN** one client IP has reached the limit
- **THEN** a request from a different client IP is processed

#### Scenario: Window expires
- **WHEN** a client IP was rejected and 60 seconds have passed since its oldest counted request
- **THEN** its next request is processed

### Requirement: Upstream failure response
If the answer cannot be generated because the language model or embedding service fails, `POST /api/chat` SHALL respond `503` with a JSON body `{"detail": string}`, and `POST /api/chat/stream` SHALL end its stream with an `error` event whose data is `{"detail": string}`, after any `delta` events already sent. Neither MAY expose internal details (stack traces, keys, provider error bodies).

#### Scenario: Model provider unavailable
- **WHEN** the language model call fails while answering a valid question
- **THEN** the response is `503` with a generic `detail` message

#### Scenario: Model provider unavailable on the stream
- **WHEN** the language model call fails while answering a valid question sent to `POST /api/chat/stream`
- **THEN** the response is `200` and the stream ends with an `error` event with a generic `detail` message and no `done` event

#### Scenario: Model fails in the middle of a streamed answer
- **WHEN** the language model fails after part of the answer was sent as `delta` events
- **THEN** the stream ends with an `error` event and no `done` event

### Requirement: Unanswered questions are not part of the conversation
A question that is not answered SHALL NOT become part of its conversation, and MUST NOT change when the conversation expires. On `POST /api/chat` a question is answered when it receives `200`. On `POST /api/chat/stream` a question is answered only when its `done` event is sent; a stream that ends with an `error` event, or that ends before `done` for any other reason (such as the client disconnecting), leaves the question unanswered.

#### Scenario: Failed follow-up is left out
- **WHEN** a question in a conversation receives `503` and the next question in that conversation is answered
- **THEN** the next answer is generated without the failed question

#### Scenario: Failed question does not extend the conversation
- **WHEN** a question in a conversation receives `503` 10 minutes after its most recent answered question, and another question is sent 6 minutes after that
- **THEN** the response is `404`

#### Scenario: Failed streamed follow-up is left out
- **WHEN** a question sent to `POST /api/chat/stream` in a conversation ends with an `error` event and the next question in that conversation is answered
- **THEN** the next answer is generated without the failed question

#### Scenario: Failed first streamed question leaves no conversation
- **WHEN** a question sent to `POST /api/chat/stream` without `conversation_id` ends with an `error` event
- **THEN** the stream carries no `conversation_id`, and the question is part of no conversation
