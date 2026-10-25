# Spec Delta

## MODIFIED Requirements

### Requirement: Document embeddings are computed only at ingestion
Embeddings of help-center documents SHALL be computed only by the ingestion command. Answering a question MUST NOT compute embeddings of any help-center document.

#### Scenario: Chat request embeds only the question
- **WHEN** the first question of a conversation is sent to the support chat API after ingestion
- **THEN** exactly one text is embedded for that request: the question itself

#### Scenario: Follow-up embeds only the self-contained question
- **WHEN** a question that continues a conversation is sent to the support chat API after ingestion
- **THEN** exactly one text is embedded for that request: the self-contained question
