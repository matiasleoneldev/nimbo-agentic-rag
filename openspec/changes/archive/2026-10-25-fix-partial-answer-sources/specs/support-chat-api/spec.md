## MODIFIED Requirements

### Requirement: No-information answer
When the retrieved indexed documents contain none of the information needed to answer the question, the system SHALL return `200` with an `answer` that explicitly says the help center does not have that information, and an empty `sources` array. It MUST NOT guess, and MUST NOT refer the visitor to any contact channel that the documents do not provide. A question whose documents cover part of it is a partially covered question, not a no-information answer.

#### Scenario: Question outside the help center
- **WHEN** a client asks "¿Cuál es la capital de Australia?"
- **THEN** the answer says the help center does not have that information and `sources` is empty

#### Scenario: No-information answer has no sources
- **WHEN** the generated answer declares that the documents cover none of the question, and it cites retrieved documents
- **THEN** the response `sources` is empty

### Requirement: Partially covered questions
When the retrieved indexed documents cover only part of a question, the `answer` SHALL answer the covered part and state explicitly which part the help center has no information about. `sources` SHALL list the documents used for the covered part.

#### Scenario: Mixed question
- **WHEN** a client asks "¿Cuánto cuesta un retiro inmediato y cuál es la capital de Australia?"
- **THEN** the answer gives the NIM-020 fee, says the help center has no information about the other part, and `sources` includes NIM-020

#### Scenario: Partial answer keeps its sources
- **WHEN** the generated answer declares that the documents cover only part of the question, and it cites NIM-020
- **THEN** the response `sources` contains NIM-020
