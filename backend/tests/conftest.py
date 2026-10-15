import dataclasses
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_postgres import PGEngine, PGVectorStore

from nimbo.config import ENV_FILE, Settings, load_settings
from tests.fakes import VECTOR_SIZE, CountingFakeEmbeddings
from tests.help_center_factory import write_help_center

load_dotenv(ENV_FILE)
os.environ["LANGSMITH_TRACING"] = "false"

# docker compose `db` service; requires `docker compose up -d db`.
DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://nimbo:nimbo@localhost:5432/nimbo_test"


@pytest.fixture(scope="session")
def engine() -> Iterator[PGEngine]:
    pg_engine = PGEngine.from_connection_string(
        url=os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    )
    # ponytail: PGEngine.close() is async-only; the pool dies with the test process.
    yield pg_engine


@pytest.fixture
def settings(tmp_path: Path, engine: PGEngine) -> Iterator[Settings]:
    """Settings pointing at a generated help center and a throwaway index table."""
    manifest = write_help_center(tmp_path)
    test_settings = dataclasses.replace(
        load_settings(),
        manifest_path=manifest,
        help_center_dir=tmp_path,
        vector_size=VECTOR_SIZE,
        table=f"test_{uuid.uuid4().hex[:12]}",
    )
    yield test_settings
    engine.drop_table(test_settings.table)


def indexed_documents(settings: Settings, engine: PGEngine) -> list[Document]:
    store = PGVectorStore.create_sync(
        engine=engine, table_name=settings.table, embedding_service=CountingFakeEmbeddings()
    )
    return store.similarity_search("", k=1000)
