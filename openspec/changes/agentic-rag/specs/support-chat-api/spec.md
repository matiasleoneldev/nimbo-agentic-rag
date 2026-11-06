## ADDED Requirements

### Requirement: Help-center searches
To answer a question, the system SHALL search the indexed documents at least once, and as many more times as it decides. It MUST write each search query itself from the question and the earlier exchanges of the conversation, so that the query is self-contained. A question SHALL get at most the configured maximum number of searches; once that number is reached, the answer MUST be generated from the documents already retrieved.

#### Scenario: Referential follow-up retrieves the right document
- **WHEN** a client asks "¿Cuánto cuesta un retiro inmediato?" and then, in the same conversation, "¿y cuánto tarda?"
- **THEN** the second answer gives the instant withdrawal timing (minutes) and `sources` includes NIM-013

#### Scenario: Question that needs two documents
- **WHEN** a client asks "¿Cuánto cuesta un retiro inmediato y cuánto tarda?"
- **THEN** the answer gives the instant withdrawal fee and its timing, and `sources` includes NIM-020 and NIM-013

#### Scenario: Documents of every search are retrieved for the question
- **WHEN** a question gets two searches that retrieve different documents, and the generated answer cites one document from each search
- **THEN** the response `sources` contains both documents

#### Scenario: Search limit
- **WHEN** the configured maximum is 3 searches and more searches are requested while answering a question
- **THEN** exactly 3 searches run and the question is answered with the documents they retrieved

#### Scenario: Answer without a search has no sources
- **WHEN** the model returns an answer before any search has run (despite the required first search), and it cites a document id
- **THEN** the response `sources` is empty

## MODIFIED Requirements

### Requirement: Answers are grounded in help-center documents
The `answer` SHALL be based only on the content of the indexed documents retrieved for the question, which are the documents returned by all of its searches, without duplicates. It MUST NOT state facts about Nimbo that those documents do not contain. Earlier exchanges of the conversation SHALL be used only to understand what the question asks: a fact stated in an earlier answer MUST NOT be used unless the documents retrieved for the current question contain it.

#### Scenario: Fee question answered from the fee document
- **WHEN** a client asks "¿Cuánto cuesta un retiro inmediato a mi cuenta bancaria?"
- **THEN** the answer states the fee given in NIM-020 (1,5% of the amount, with the per-country minimum) and `sources` includes NIM-020

#### Scenario: Comparison across turns
- **WHEN** a client asks "¿Cuánto cuesta un retiro inmediato?" and then, in the same conversation, "¿y es más caro que el retiro estándar?"
- **THEN** the second answer compares both fees (the standard withdrawal is free), every fact in it is stated in the documents retrieved for the second question, and `sources` lists the documents those facts come from

#### Scenario: Question about Nimbo is searched
- **WHEN** a client asks a question about Nimbo's products, fees or policies
- **THEN** at least one search runs before the answer is generated, and the answer is based on the documents it retrieved

### Requirement: Follow-up questions use the conversation
When answering a question that continues a conversation, the system SHALL take into account the earlier answered questions and answers of that conversation, up to its 6 most recent exchanges (an exchange is one question and its answer). Older exchanges MUST NOT be used. A conversation holds only questions and answers, never the searches made for them nor the documents retrieved for them.

#### Scenario: Follow-up understood from the conversation
- **WHEN** a client asks "¿Cuál es el mínimo por retiro inmediato?" and then, in the same conversation, "¿y en Chile?"
- **THEN** the second answer gives the Chile minimum (500 CLP) and `sources` includes NIM-020

#### Scenario: Only the 6 most recent exchanges are used
- **WHEN** a conversation has 7 answered exchanges and an 8th question is sent in it
- **THEN** the 8th answer is generated with exchanges 2 to 7 and without the first exchange

#### Scenario: Searches are not part of the conversation
- **WHEN** a question is answered after a search, and a follow-up is sent in the same conversation
- **THEN** the follow-up is generated with the earlier question and answer, and without the earlier search query or the documents it retrieved

### Requirement: Streamed answer events
Each event SHALL carry a JSON object in its `data` field. Zero or more `delta` events (`{"text": string}`) MUST come first; their texts, in order, are the answer written so far. The stream MUST end with exactly one `done` or `error` event. `done` carries the body `POST /api/chat` returns on `200`, and its `answer` is authoritative: it MAY differ from the joined `delta` texts.

#### Scenario: Deltas carry the answer as it is written
- **WHEN** the answer "Te cobramos 1,5%." is generated for a question sent to `POST /api/chat/stream`
- **THEN** the `delta` texts, joined in order, read "Te cobramos 1,5%." and are followed by a `done` event whose `answer` is "Te cobramos 1,5%."

#### Scenario: Done event carries sources and conversation data
- **WHEN** a streamed answer is based on NIM-020
- **THEN** the `done` event contains the `answer`, `sources` with `{"id": "NIM-020", "title": "<NIM-020 manifest title>"}`, a `conversation_id` and `expires_in_seconds` `900`

#### Scenario: Only the answer text is streamed
- **WHEN** a question that gets a search is sent to `POST /api/chat/stream`
- **THEN** no `delta` text contains the search query, the question language, the coverage or any source id

#### Scenario: Same answer rules on both endpoints
- **WHEN** the generated answer cites an id that was not among the documents retrieved for the question, sent to `POST /api/chat/stream`
- **THEN** that id does not appear in the `done` event `sources`

## REMOVED Requirements

### Requirement: Retrieval for follow-up questions
**Reason**: There is no separate rewrite step anymore. The model writes every search query itself, for first questions as well as follow-ups, so a first question is no longer searched exactly as sent.
**Migration**: Covered by the new "Help-center searches" requirement, which keeps the "Referential follow-up retrieves the right document" scenario.
