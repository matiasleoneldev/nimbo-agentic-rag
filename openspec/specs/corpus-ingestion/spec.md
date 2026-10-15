# corpus-ingestion Specification

## Purpose

Turns the Nimbo help-center documents into the searchable index the support chat answers from: decides which documents are indexed, what text and metadata each one contributes, and when embeddings are computed.

## Requirements

### Requirement: Indexed documents come from the manifest's documents folder
The ingestion command SHALL index exactly the help-center manifest entries whose `file_path` is under `documents/`. Entries under any other folder (such as `updates/`) MUST NOT be indexed. Each indexed help-center document is identified by its manifest `id`.

#### Scenario: Only documents/ entries are indexed
- **WHEN** the ingestion command runs against a manifest with entries under `documents/` and an entry under `updates/`
- **THEN** the index contains one indexed document per `documents/` entry
- **AND** the index contains no indexed document for the `updates/` entry

#### Scenario: Real corpus produces one indexed document per id
- **WHEN** the ingestion command runs against `nimbo-help-center/manifest.json`
- **THEN** the index contains 25 indexed documents with 25 distinct ids, and NIM-020 is indexed from `documents/NIM-020-comisiones-cuenta-personal.pdf`

### Requirement: Indexed documents carry manifest metadata
Each indexed document SHALL store its manifest `id`, `title`, `category`, `products`, `countries` and `updated_at`, so answers can cite it by id and title.

#### Scenario: Metadata is stored
- **WHEN** a manifest entry is ingested
- **THEN** its indexed document exposes the same `id`, `title`, `category`, `products`, `countries` and `updated_at` values as the manifest entry

### Requirement: Table rows stay together in extracted text
When a help-center document contains a table, the extracted text SHALL keep each table row's cells together on one line, in row order, so that every value stays next to the label it belongs to.

#### Scenario: Fee table row is preserved
- **WHEN** a document containing a table row with the cells "Retiro inmediato a cuenta bancaria" and "1,5% del monto, con el mínimo de la tabla siguiente" is ingested
- **THEN** the indexed text contains a single line holding both cells

### Requirement: Re-running ingestion replaces the index
Each run of the ingestion command SHALL leave the index containing only the indexed documents of that run. Running it twice MUST NOT produce duplicates.

#### Scenario: Second run does not duplicate
- **WHEN** the ingestion command runs twice against the same manifest
- **THEN** the index contains each indexed document exactly once

### Requirement: Ingestion fails before indexing when a document is unreadable
If a selected manifest entry points to a file that does not exist or cannot be read as a PDF, the ingestion command SHALL exit with a non-zero status and an error message naming that `file_path`, and MUST NOT modify the existing index.

#### Scenario: Missing file
- **WHEN** a `documents/` manifest entry points to a file that does not exist
- **THEN** the command exits with a non-zero status, the error names the missing `file_path`, and the previously stored index is unchanged

### Requirement: Document embeddings are computed only at ingestion
Embeddings of help-center documents SHALL be computed only by the ingestion command. Answering a question MUST NOT compute embeddings of any help-center document.

#### Scenario: Chat request embeds only the question
- **WHEN** a question is sent to the support chat API after ingestion
- **THEN** exactly one text is embedded for that request: the question itself
