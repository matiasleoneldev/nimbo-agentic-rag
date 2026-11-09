# Spec Delta

## ADDED Requirements

### Requirement: Small talk
A question is small talk when it only greets, thanks, says goodbye or asks in general what the chat can do, and asks nothing else. Small talk SHALL be answered without searching the indexed documents, with an empty `sources` array. Its `answer` MUST NOT state facts about Nimbo and MUST NOT say that the help center does not have the information. A question that also asks anything else, or that asks about the visitor's account, is not small talk.

#### Scenario: Greeting
- **WHEN** a client asks "Hola"
- **THEN** no search runs, the answer greets the visitor without saying that the help center does not have that information, and `sources` is empty

#### Scenario: Thanks after an answer
- **WHEN** a client asks "¿Cuánto cuesta un retiro inmediato?" and then, in the same conversation, "¡Gracias!"
- **THEN** no search runs for the second question, and its `sources` is empty

#### Scenario: What the chat can do
- **WHEN** a client asks "¿Qué podés hacer?"
- **THEN** no search runs, the answer says that the chat answers questions using Nimbo's help center and that it cannot see the visitor's account, it states no facts about Nimbo's products, fees or policies, and `sources` is empty

#### Scenario: Greeting with a question
- **WHEN** a client asks "Hola, ¿cuánto cuesta un retiro inmediato?"
- **THEN** at least one search runs, the answer states the NIM-020 fee, and `sources` includes NIM-020

#### Scenario: Thanks with a follow-up
- **WHEN** a client asks "¿Cuál es el mínimo por retiro inmediato?" and then, in the same conversation, "Gracias, ¿y en Chile?"
- **THEN** at least one search runs for the second question, its answer gives the Chile minimum (500 CLP), and `sources` includes NIM-020

#### Scenario: Account question is not small talk
- **WHEN** a client asks "¿Podés ver mi cuenta?"
- **THEN** at least one search runs, and the answer says that the chat cannot see the visitor's account

## MODIFIED Requirements

### Requirement: Answers are grounded in help-center documents
Except for small talk, the `answer` SHALL be based only on the content of the indexed documents retrieved for the question, which are the documents returned by all of its searches, without duplicates. It MUST NOT state facts about Nimbo that those documents do not contain. Earlier exchanges of the conversation SHALL be used only to understand what the question asks: a fact stated in an earlier answer MUST NOT be used unless the documents retrieved for the current question contain it.

#### Scenario: Fee question answered from the fee document
- **WHEN** a client asks "¿Cuánto cuesta un retiro inmediato a mi cuenta bancaria?"
- **THEN** the answer states the fee given in NIM-020 (1,5% of the amount, with the per-country minimum) and `sources` includes NIM-020

#### Scenario: Comparison across turns
- **WHEN** a client asks "¿Cuánto cuesta un retiro inmediato?" and then, in the same conversation, "¿y es más caro que el retiro estándar?"
- **THEN** the second answer compares both fees (the standard withdrawal is free), every fact in it is stated in the documents retrieved for the second question, and `sources` lists the documents those facts come from

#### Scenario: Question about Nimbo is searched
- **WHEN** a client asks a question about Nimbo's products, fees or policies
- **THEN** at least one search runs before the answer is generated, and the answer is based on the documents it retrieved

### Requirement: Help-center searches
To answer a question that is not small talk, the system SHALL search the indexed documents at least once, and as many more times as it decides. It MUST write each search query itself from the question and the earlier exchanges of the conversation, so that the query is self-contained. A question SHALL get at most the configured maximum number of searches; once that number is reached, the answer MUST be generated from the documents already retrieved.

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
- **WHEN** the model returns an answer before any search has run, and it cites a document id
- **THEN** the response `sources` is empty
