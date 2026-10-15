"""Builds the help-center index: `python -m nimbo.ingest` (run from backend/)."""

import json
import sys
import uuid
from typing import Any, TypedDict

from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGEngine, PGVectorStore
from pdfplumber.utils.exceptions import PdfminerException

from nimbo.config import ENV_FILE, Settings, load_settings, require_env
from nimbo.pdf_text import extract_text

# Only this folder is indexed; `updates/` is reserved for a later re-indexing change.
INDEXED_FOLDER = "documents/"


class ManifestEntry(TypedDict):
    file_path: str
    id: str
    title: str
    category: str
    products: list[str]
    countries: list[str]
    updated_at: str


class IngestionError(Exception):
    pass


def _header(entry: ManifestEntry, labels: dict[str, dict[str, str]]) -> str:
    """Metadata lines prepended to the document text before embedding."""
    products = ", ".join(labels["products"][p] for p in entry["products"])
    countries = ", ".join(labels["countries"][c] for c in entry["countries"])
    return (
        f"{entry['id']}: {entry['title']}\n"
        f"Categoría: {labels['categories'][entry['category']]}\n"
        f"Aplica a: {products}\n"
        f"Países: {countries}"
    )


def ingest(settings: Settings, embeddings: Embeddings, engine: PGEngine) -> int:
    """Replaces the index with the manifest's `documents/` entries. Returns how many."""
    manifest: list[ManifestEntry] = json.loads(settings.manifest_path.read_text(encoding="utf-8"))
    entries = [e for e in manifest if e["file_path"].startswith(INDEXED_FOLDER)]

    # Read everything before touching the index, so a bad file leaves it unchanged.
    texts: list[str] = []
    for entry in entries:
        path = settings.help_center_dir / entry["file_path"]
        try:
            body = extract_text(path)
        except (OSError, PdfminerException) as exc:
            raise IngestionError(f"Cannot read {entry['file_path']}: {exc}") from exc
        texts.append(f"{_header(entry, settings.labels)}\n\n{body}")
    vectors = embeddings.embed_documents(texts)

    metadatas: list[dict[str, Any]] = [
        {
            "id": e["id"],
            "title": e["title"],
            "category": e["category"],
            "products": e["products"],
            "countries": e["countries"],
            "updated_at": e["updated_at"],
        }
        for e in entries
    ]
    # ponytail: drop + recreate is not atomic; on a DB failure, re-run the command.
    engine.drop_table(settings.table)
    engine.init_vectorstore_table(table_name=settings.table, vector_size=settings.vector_size)
    store = PGVectorStore.create_sync(
        engine=engine, table_name=settings.table, embedding_service=embeddings
    )
    store.add_embeddings(
        texts,
        vectors,
        metadatas=metadatas,
        ids=[str(uuid.uuid5(uuid.NAMESPACE_URL, e["id"])) for e in entries],
    )
    return len(entries)


def main() -> int:
    load_dotenv(ENV_FILE)
    settings = load_settings()
    # ponytail: PGEngine.close() is async-only; the pool dies with this short-lived process.
    engine = PGEngine.from_connection_string(url=require_env("DATABASE_URL"))
    try:
        count = ingest(settings, OpenAIEmbeddings(model=settings.embedding_model), engine)
    except IngestionError as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        return 1
    print(f"Indexed {count} documents into table '{settings.table}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
