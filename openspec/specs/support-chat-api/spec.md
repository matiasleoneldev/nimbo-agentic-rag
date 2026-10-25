# support-chat-api Specification

## Purpose

Defines the public HTTP contract of the Nimbo support chat: a single plain-text question in, a grounded answer with its source help-center documents out, plus validation, rate limiting and error behavior.

## Requirements

### Requirement: Ask endpoint
The system SHALL expose `POST /api/chat`, accepting a JSON body `{"question": string, "conversation_id"?: string}` and responding `200` with `{"answer": string, "sources": [{"id": string, "title": string}], "conversation_id": string, "expires_in_seconds": integer}`. A question MUST NOT be influenced by the questions or answers of any other conversation. The endpoint MUST NOT require authentication.

#### Scenario: Successful answer
- **WHEN** an unauthenticated client sends `{"question": "¿Cuánto cuesta un retiro inmediato?"}`
- **THEN** the response is `200` with a non-empty `answer` string, a `sources` array, a `conversation_id` string and an `expires_in_seconds` integer

#### Scenario: Requests are independent
- **WHEN** a client sends two questions in a row, the second one without `conversation_id`
- **THEN** the second answer is produced only from the second question and the documents retrieved for it

### Requirement: Question validation
The `question` SHALL be a string that, after trimming surrounding whitespace, has between 1 and 500 characters. When present, `conversation_id` SHALL be a string of at most 64 characters. Any other body (missing field, non-string, empty or whitespace-only, longer than 500 characters, `conversation_id` that is not a string or is longer than 64 characters, malformed JSON) MUST be rejected with `422` without generating an answer.

#### Scenario: Empty question
- **WHEN** a client sends `{"question": "   "}`
- **THEN** the response is `422`

#### Scenario: Too long question
- **WHEN** a client sends a question of 501 characters
- **THEN** the response is `422`

#### Scenario: Maximum length accepted
- **WHEN** a client sends a question of exactly 500 characters
- **THEN** the request is not rejected for its length

#### Scenario: Non-string question
- **WHEN** a client sends `{"question": 42}`
- **THEN** the response is `422`

#### Scenario: Non-string conversation id
- **WHEN** a client sends `{"question": "Hola", "conversation_id": 42}`
- **THEN** the response is `422`

#### Scenario: Too long conversation id
- **WHEN** a client sends a `conversation_id` of 65 characters
- **THEN** the response is `422`

### Requirement: Answers are grounded in help-center documents
The `answer` SHALL be based only on the content of the indexed documents retrieved for the question, and MUST NOT state facts about Nimbo that those documents do not contain. Earlier exchanges of the conversation SHALL be used only to understand what the question asks: a fact stated in an earlier answer MUST NOT be used unless the documents retrieved for the current question contain it.

#### Scenario: Fee question answered from the fee document
- **WHEN** a client asks "¿Cuánto cuesta un retiro inmediato a mi cuenta bancaria?"
- **THEN** the answer states the fee given in NIM-020 (1,5% of the amount, with the per-country minimum) and `sources` includes NIM-020

#### Scenario: Comparison across turns
- **WHEN** a client asks "¿Cuánto cuesta un retiro inmediato?" and then, in the same conversation, "¿y es más caro que el retiro estándar?"
- **THEN** the second answer compares both fees (the standard withdrawal is free), every fact in it is stated in the documents retrieved for the second question, and `sources` lists the documents those facts come from

### Requirement: Sources list the documents the answer used
`sources` SHALL list, without duplicates, each indexed document the answer is based on, with its `id` and `title`. It MUST only contain ids of documents retrieved for that question; any other id MUST be omitted.

#### Scenario: Cited sources are returned with titles
- **WHEN** the answer is based on NIM-020
- **THEN** `sources` contains `{"id": "NIM-020", "title": "<NIM-020 manifest title>"}` exactly once

#### Scenario: Unknown ids are dropped
- **WHEN** the generated answer cites an id that was not among the documents retrieved for the question
- **THEN** that id does not appear in `sources`

#### Scenario: Sources of earlier answers are not carried over
- **WHEN** an earlier answer in the conversation had NIM-020 in its `sources` and the current generated answer cites no document
- **THEN** the current response `sources` is empty

### Requirement: No-information answer
When the retrieved indexed documents do not contain the information needed to answer, the system SHALL return `200` with an `answer` that explicitly says the help center does not have that information, and an empty `sources` array. It MUST NOT guess, and MUST NOT refer the visitor to any contact channel that the documents do not provide.

#### Scenario: Question outside the help center
- **WHEN** a client asks "¿Cuál es la capital de Australia?"
- **THEN** the answer says the help center does not have that information and `sources` is empty

#### Scenario: No-information answer has no sources
- **WHEN** the generated answer declares that the documents do not contain the information
- **THEN** the response `sources` is empty

### Requirement: Answer language follows the question
The `answer` SHALL be written in the language of the question being answered, whatever that language is, even though the indexed documents are in Spanish and earlier exchanges of the conversation are in another language.

#### Scenario: English question
- **WHEN** a client asks "How much does an instant withdrawal to my bank account cost?"
- **THEN** the answer is in English, states the NIM-020 fee, and `sources` includes NIM-020

#### Scenario: Spanish question
- **WHEN** a client asks a question in Spanish
- **THEN** the answer is in Spanish

#### Scenario: Language changes within a conversation
- **WHEN** a client asks a question in English and then, in the same conversation, a follow-up in Spanish
- **THEN** the second answer is in Spanish

### Requirement: Spanish answers use voseo
Answers in Spanish SHALL address the visitor with voseo ("vos", "tenés", "hacé"), matching the help-center documents.

#### Scenario: Voseo in Spanish answer
- **WHEN** a client asks "¿Cómo activo la verificación en dos pasos?"
- **THEN** the answer addresses the visitor with voseo forms and not with "tú" or "usted" forms

### Requirement: Variants by country and account type
When the information asked about differs by country or by account type and the question does not say which applies, the `answer` SHALL include every applicable variant, each labeled with its country or account type.

#### Scenario: Fee minimum by country
- **WHEN** a client asks "¿Cuál es el mínimo por retiro inmediato?" without naming a country
- **THEN** the answer gives the minimum for Argentina, México, Colombia and Chile, each labeled

#### Scenario: Country given
- **WHEN** a client asks "¿Cuál es el mínimo por retiro inmediato en Chile?"
- **THEN** the answer gives the Chile minimum (500 CLP)

### Requirement: Partially covered questions
When the retrieved indexed documents cover only part of a question, the `answer` SHALL answer the covered part and state explicitly which part the help center has no information about. `sources` lists the documents used for the covered part.

#### Scenario: Mixed question
- **WHEN** a client asks "¿Cuánto cuesta un retiro inmediato y cuál es la capital de Australia?"
- **THEN** the answer gives the NIM-020 fee, says the help center has no information about the other part, and `sources` includes NIM-020

### Requirement: No access to user accounts
The system has no access to any visitor's account data. When a question asks about the visitor's own account, payments or balance, the `answer` SHALL state that the chat cannot see accounts, and give the general information the documents provide on the topic.

#### Scenario: Account-specific question
- **WHEN** a client asks "¿Por qué rechazaron mi pago de ayer?"
- **THEN** the answer says the chat cannot see the visitor's account and explains the general reasons a payment can be declined, with `sources` including NIM-032

### Requirement: Sensitive data reminder
When a question contains what looks like sensitive data (a password, a verification code, or a card number), the `answer` SHALL remind the visitor not to share that kind of data, and MUST NOT repeat the sensitive value, neither in that answer nor in any later answer of the conversation.

#### Scenario: Card number in question
- **WHEN** a client asks "Mi tarjeta 4111 1111 1111 1111 no funciona, ¿qué hago?"
- **THEN** the answer reminds the visitor not to share card data and does not contain "4111 1111 1111 1111"

#### Scenario: Card number in an earlier question
- **WHEN** a client asks "Mi tarjeta 4111 1111 1111 1111 no funciona, ¿qué hago?" and then, in the same conversation, "¿y si sigue sin funcionar?"
- **THEN** the second answer does not contain "4111 1111 1111 1111"

### Requirement: Answers are plain text
The `answer` SHALL be plain text. Line breaks MAY separate steps or items; it MUST NOT contain HTML or Markdown markup.

#### Scenario: Step-by-step answer
- **WHEN** a client asks "¿Cómo activo la verificación en dos pasos?"
- **THEN** the answer contains no HTML tags and no Markdown markup

### Requirement: Per-IP rate limit
The system SHALL accept at most 10 requests to `POST /api/chat` per client IP address in any 60-second window. Further requests in that window MUST be rejected with `429` and a `Retry-After` header (seconds), without generating an answer. Every request that is not rejected with `429` counts toward the limit, including requests rejected with `422`; `429` responses do not extend the window.

#### Scenario: Eleventh request in a minute is rejected
- **WHEN** a client IP sends 11 requests within 60 seconds
- **THEN** the first 10 are processed and the 11th receives `429` with a `Retry-After` header

#### Scenario: Limit is per IP
- **WHEN** one client IP has reached the limit
- **THEN** a request from a different client IP is processed

#### Scenario: Window expires
- **WHEN** a client IP was rejected and 60 seconds have passed since its oldest counted request
- **THEN** its next request is processed

### Requirement: Upstream failure response
If the answer cannot be generated because the language model or embedding service fails, the system SHALL respond `503` with a JSON body `{"detail": string}` that does not expose internal details (stack traces, keys, provider error bodies).

#### Scenario: Model provider unavailable
- **WHEN** the language model call fails while answering a valid question
- **THEN** the response is `503` with a generic `detail` message

### Requirement: Conversations
A question sent without `conversation_id` SHALL start a new conversation, and its response MUST carry a `conversation_id` that no other conversation uses. A question sent with the `conversation_id` of an open conversation SHALL continue that conversation, and its response MUST carry the same `conversation_id`. Clients MUST treat `conversation_id` as opaque.

#### Scenario: First question starts a conversation
- **WHEN** a client sends a question without `conversation_id`
- **THEN** the response is `200` with a non-empty `conversation_id`

#### Scenario: Follow-up continues the conversation
- **WHEN** a client sends a question with the `conversation_id` returned by its previous answer
- **THEN** the response is `200` and carries the same `conversation_id`

#### Scenario: New conversations get different ids
- **WHEN** two questions are sent without `conversation_id`
- **THEN** their responses carry different `conversation_id` values

### Requirement: Follow-up questions use the conversation
When answering a question that continues a conversation, the system SHALL take into account the earlier answered questions and answers of that conversation, up to its 6 most recent exchanges (an exchange is one question and its answer). Older exchanges MUST NOT be used. A conversation holds only questions and answers, never the documents retrieved for them.

#### Scenario: Follow-up understood from the conversation
- **WHEN** a client asks "¿Cuál es el mínimo por retiro inmediato?" and then, in the same conversation, "¿y en Chile?"
- **THEN** the second answer gives the Chile minimum (500 CLP) and `sources` includes NIM-020

#### Scenario: Only the 6 most recent exchanges are used
- **WHEN** a conversation has 7 answered exchanges and an 8th question is sent in it
- **THEN** the 8th answer is generated with exchanges 2 to 7 and without the first exchange

### Requirement: Retrieval for follow-up questions
For a question that continues a conversation, the indexed documents SHALL be retrieved for a self-contained question: the question rewritten so that it resolves its references to earlier exchanges and can be understood without them. The first question of a conversation SHALL be retrieved as sent.

#### Scenario: Referential follow-up retrieves the right document
- **WHEN** a client asks "¿Cuánto cuesta un retiro inmediato?" and then, in the same conversation, "¿y cuánto tarda?"
- **THEN** the second answer gives the instant withdrawal timing (minutes) and `sources` includes NIM-013

### Requirement: Conversation expiry
A conversation SHALL expire 15 minutes after its most recent answered question. `expires_in_seconds` MUST state the whole seconds left until the conversation expires, counted from the response. A question sent with a `conversation_id` that is unknown or expired MUST be rejected with `404` and a JSON body `{"detail": string}`, without generating an answer. A restart of the system ends every conversation.

#### Scenario: Remaining time is reported
- **WHEN** a question is answered
- **THEN** the response `expires_in_seconds` is `900`

#### Scenario: Expired conversation
- **WHEN** a client sends a question with a `conversation_id` whose most recent answered question was more than 15 minutes ago
- **THEN** the response is `404` with a `detail` message and no answer is generated

#### Scenario: Unknown conversation
- **WHEN** a client sends a question with a `conversation_id` the system never returned
- **THEN** the response is `404` and no answer is generated

#### Scenario: Activity keeps the conversation open
- **WHEN** a question is answered 14 minutes after the previous answered question of the same conversation, and another question is sent 14 minutes after that
- **THEN** the last question is answered in the same conversation

### Requirement: Unanswered questions are not part of the conversation
A question that is not answered (any response other than `200`) SHALL NOT become part of its conversation, and MUST NOT change when the conversation expires.

#### Scenario: Failed follow-up is left out
- **WHEN** a question in a conversation receives `503` and the next question in that conversation is answered
- **THEN** the next answer is generated without the failed question

#### Scenario: Failed question does not extend the conversation
- **WHEN** a question in a conversation receives `503` 10 minutes after its most recent answered question, and another question is sent 6 minutes after that
- **THEN** the response is `404`
