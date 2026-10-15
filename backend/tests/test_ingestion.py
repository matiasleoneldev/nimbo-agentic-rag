import dataclasses

import pytest
from langchain_postgres import PGEngine

from nimbo.config import Settings, load_settings
from nimbo.ingest import IngestionError, ingest
from tests.conftest import indexed_documents
from tests.fakes import CountingFakeEmbeddings
from tests.help_center_factory import MANIFEST


def test_ingest_indexes_only_documents_folder(settings: Settings, engine: PGEngine) -> None:
    count = ingest(settings, CountingFakeEmbeddings(), engine)

    docs = indexed_documents(settings, engine)
    assert count == 2
    assert sorted(d.metadata["id"] for d in docs) == ["NIM-004", "NIM-020"]
    nim_020 = next(d for d in docs if d.metadata["id"] == "NIM-020")
    assert "1,5% del monto" in nim_020.page_content
    assert "1,2% del monto" not in nim_020.page_content  # the updates/ version


def test_ingest_stores_manifest_metadata(settings: Settings, engine: PGEngine) -> None:
    ingest(settings, CountingFakeEmbeddings(), engine)

    doc = next(d for d in indexed_documents(settings, engine) if d.metadata["id"] == "NIM-004")
    entry = MANIFEST[0]
    for key in ("id", "title", "category", "products", "countries", "updated_at"):
        assert doc.metadata[key] == entry[key]


def test_ingest_twice_does_not_duplicate(settings: Settings, engine: PGEngine) -> None:
    ingest(settings, CountingFakeEmbeddings(), engine)
    ingest(settings, CountingFakeEmbeddings(), engine)

    assert len(indexed_documents(settings, engine)) == 2


def test_ingest_missing_file_fails_and_keeps_index(settings: Settings, engine: PGEngine) -> None:
    ingest(settings, CountingFakeEmbeddings(), engine)
    missing = settings.help_center_dir / MANIFEST[0]["file_path"]
    missing.unlink()

    with pytest.raises(IngestionError, match=MANIFEST[0]["file_path"]):
        ingest(settings, CountingFakeEmbeddings(), engine)

    assert len(indexed_documents(settings, engine)) == 2


def test_ingest_real_corpus_indexes_25_documents(settings: Settings, engine: PGEngine) -> None:
    real = load_settings()
    if not real.manifest_path.exists():
        pytest.skip("real help center (git-ignored) is not present")
    real_settings = dataclasses.replace(
        real, vector_size=settings.vector_size, table=settings.table
    )

    count = ingest(real_settings, CountingFakeEmbeddings(), engine)

    docs = indexed_documents(real_settings, engine)
    assert count == 25
    assert len({d.metadata["id"] for d in docs}) == 25
    nim_020 = next(d for d in docs if d.metadata["id"] == "NIM-020")
    assert (
        "Retiro inmediato a cuenta bancaria | 1,5% del monto, con el mínimo de la tabla siguiente"
        in nim_020.page_content.splitlines()
    )
