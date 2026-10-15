# Spec Delta

## Purpose

Defines the public HTTP contract of the Nimbo support chat: a single plain-text question in, a grounded answer with its source help-center documents out, plus validation, rate limiting and error behavior.

## ADDED Requirements

### Requirement: Ask endpoint
The system SHALL expose `POST /api/chat`, accepting a JSON body `{"question": string}` and responding `200` with `{"answer": string, "sources": [{"id": string, "title": string}]}`. Each request is answered independently: no previous question or answer influences it. The endpoint MUST NOT require authentication.

#### Scenario: Successful answer
- **WHEN** an unauthenticated client sends `{"question": "¿Cuánto cuesta un retiro inmediato?"}`
- **THEN** the response is `200` with a non-empty `answer` string and a `sources` array

#### Scenario: Requests are independent
- **WHEN** a client sends two questions in a row
- **THEN** the second answer is produced only from the second question and the documents retrieved for it

### Requirement: Question validation
The `question` SHALL be a string that, after trimming surrounding whitespace, has between 1 and 500 characters. Any other body (missing field, non-string, empty or whitespace-only, longer than 500 characters, malformed JSON) MUST be rejected with `422` without generating an answer.

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

### Requirement: Answers are grounded in help-center documents
The `answer` SHALL be based only on the content of the indexed documents retrieved for the question, and MUST NOT state facts about Nimbo that those documents do not contain.

#### Scenario: Fee question answered from the fee document
- **WHEN** a client asks "¿Cuánto cuesta un retiro inmediato a mi cuenta bancaria?"
- **THEN** the answer states the fee given in NIM-020 (1,5% of the amount, with the per-country minimum) and `sources` includes NIM-020

### Requirement: Sources list the documents the answer used
`sources` SHALL list, without duplicates, each indexed document the answer is based on, with its `id` and `title`. It MUST only contain ids of documents retrieved for that question; any other id MUST be omitted.

#### Scenario: Cited sources are returned with titles
- **WHEN** the answer is based on NIM-020
- **THEN** `sources` contains `{"id": "NIM-020", "title": "<NIM-020 manifest title>"}` exactly once

#### Scenario: Unknown ids are dropped
- **WHEN** the generated answer cites an id that was not among the documents retrieved for the question
- **THEN** that id does not appear in `sources`

### Requirement: No-information answer
When the retrieved indexed documents do not contain the information needed to answer, the system SHALL return `200` with an `answer` that explicitly says the help center does not have that information, and an empty `sources` array. It MUST NOT guess, and MUST NOT refer the visitor to any contact channel that the documents do not provide.

#### Scenario: Question outside the help center
- **WHEN** a client asks "¿Cuál es la capital de Australia?"
- **THEN** the answer says the help center does not have that information and `sources` is empty

#### Scenario: No-information answer has no sources
- **WHEN** the generated answer declares that the documents do not contain the information
- **THEN** the response `sources` is empty

### Requirement: Answer language follows the question
The `answer` SHALL be written in the language of the question, whatever that language is, even though the indexed documents are in Spanish.

#### Scenario: English question
- **WHEN** a client asks "How much does an instant withdrawal to my bank account cost?"
- **THEN** the answer is in English, states the NIM-020 fee, and `sources` includes NIM-020

#### Scenario: Spanish question
- **WHEN** a client asks a question in Spanish
- **THEN** the answer is in Spanish

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
When a question contains what looks like sensitive data (a password, a verification code, or a card number), the `answer` SHALL remind the visitor not to share that kind of data, and MUST NOT repeat the sensitive value.

#### Scenario: Card number in question
- **WHEN** a client asks "Mi tarjeta 4111 1111 1111 1111 no funciona, ¿qué hago?"
- **THEN** the answer reminds the visitor not to share card data and does not contain "4111 1111 1111 1111"

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
