from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from langchain_postgres import PGEngine

from nimbo.api import create_app, get_chat_model, get_embeddings
from nimbo.chat import ChatModel
from nimbo.config import Settings
from nimbo.ingest import ingest
from tests.fakes import (
    CountingFakeEmbeddings,
    FailingChatModel,
    RecordingFakeChatModel,
    model_reply,
)

FEE_QUESTION = "¿Cuánto cuesta un retiro inmediato?"
FEE_TITLE = "Comisiones para Cuentas Personales"

ClientFactory = Callable[[ChatModel], TestClient]


@pytest.fixture
def embeddings() -> CountingFakeEmbeddings:
    return CountingFakeEmbeddings()


@pytest.fixture
def make_client(
    settings: Settings, engine: PGEngine, embeddings: CountingFakeEmbeddings
) -> ClientFactory:
    """Ingested fake help center + an app whose OpenAI seams are replaced by fakes."""
    ingest(settings, embeddings, engine)
    embeddings.embedded_texts.clear()

    def factory(model: ChatModel) -> TestClient:
        app = create_app(settings=settings, engine=engine)
        app.dependency_overrides[get_chat_model] = lambda: model
        app.dependency_overrides[get_embeddings] = lambda: embeddings
        return TestClient(app)

    return factory


def fee_model() -> RecordingFakeChatModel:
    return RecordingFakeChatModel(responses=[model_reply("Cuesta 1,5% del monto.", ["NIM-020"])])


def test_chat_returns_answer_and_sources(make_client: ClientFactory) -> None:
    response = make_client(fee_model()).post("/api/chat", json={"question": FEE_QUESTION})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Cuesta 1,5% del monto."
    assert body["sources"] == [{"id": "NIM-020", "title": FEE_TITLE}]


def test_chat_requests_are_independent(make_client: ClientFactory) -> None:
    model = fee_model()
    client = make_client(model)

    client.post("/api/chat", json={"question": "Primera pregunta sobre comisiones"})
    client.post("/api/chat", json={"question": "Segunda pregunta"})

    second_call = model.received[1]
    assert len(second_call) == 2  # system prompt + this question only, no history
    assert "Primera pregunta" not in str(second_call[1].content)
    assert "Segunda pregunta" in str(second_call[1].content)


def test_chat_rejects_blank_question(make_client: ClientFactory) -> None:
    response = make_client(fee_model()).post("/api/chat", json={"question": "   "})

    assert response.status_code == 422


def test_chat_rejects_question_over_500_chars(make_client: ClientFactory) -> None:
    response = make_client(fee_model()).post("/api/chat", json={"question": "a" * 501})

    assert response.status_code == 422


def test_chat_accepts_question_of_500_chars(make_client: ClientFactory) -> None:
    response = make_client(fee_model()).post("/api/chat", json={"question": "a" * 500})

    assert response.status_code == 200


def test_chat_rejects_non_string_question(make_client: ClientFactory) -> None:
    response = make_client(fee_model()).post("/api/chat", json={"question": 42})

    assert response.status_code == 422


def test_chat_sources_include_titles_without_duplicates(make_client: ClientFactory) -> None:
    model = RecordingFakeChatModel(
        responses=[model_reply("Respuesta.", ["NIM-020", "NIM-004", "NIM-020"])]
    )

    body = make_client(model).post("/api/chat", json={"question": FEE_QUESTION}).json()

    assert body["sources"] == [
        {"id": "NIM-020", "title": FEE_TITLE},
        {"id": "NIM-004", "title": "Activar la verificación en dos pasos"},
    ]


def test_chat_drops_unretrieved_source_ids(make_client: ClientFactory) -> None:
    model = RecordingFakeChatModel(responses=[model_reply("Respuesta.", ["NIM-020", "NIM-999"])])

    body = make_client(model).post("/api/chat", json={"question": FEE_QUESTION}).json()

    assert [s["id"] for s in body["sources"]] == ["NIM-020"]


def test_chat_no_information_returns_empty_sources(make_client: ClientFactory) -> None:
    model = RecordingFakeChatModel(
        responses=[model_reply("El Centro de Ayuda no tiene esa información.", ["NIM-020"], False)]
    )

    response = make_client(model).post("/api/chat", json={"question": "¿Capital de Australia?"})

    assert response.status_code == 200
    assert response.json()["sources"] == []


def test_chat_rate_limit_rejects_eleventh_request(make_client: ClientFactory) -> None:
    client = make_client(fee_model())

    statuses = [
        client.post("/api/chat", json={"question": "   "}).status_code,  # 422s count too
        *[client.post("/api/chat", json={"question": FEE_QUESTION}).status_code for _ in range(9)],
    ]
    rejected = client.post("/api/chat", json={"question": FEE_QUESTION})

    assert statuses == [422] + [200] * 9
    assert rejected.status_code == 429
    assert int(rejected.headers["Retry-After"]) > 0


def test_chat_returns_503_when_model_fails(make_client: ClientFactory) -> None:
    response = make_client(FailingChatModel(responses=[])).post(
        "/api/chat", json={"question": FEE_QUESTION}
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "The assistant is temporarily unavailable. Please try again later."
    }


def test_chat_embeds_only_question(
    make_client: ClientFactory, embeddings: CountingFakeEmbeddings
) -> None:
    make_client(fee_model()).post("/api/chat", json={"question": FEE_QUESTION})

    assert embeddings.embedded_texts == [FEE_QUESTION]
