from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import BaseMessage
from langchain_postgres import PGEngine

from nimbo.api import create_app, get_chat_model, get_embeddings
from nimbo.chat import ChatModel
from nimbo.config import Settings
from nimbo.ingest import ingest
from tests.fakes import (
    FAIL,
    CountingFakeEmbeddings,
    FailingChatModel,
    FakeClock,
    FlakyChatModel,
    RecordingFakeChatModel,
    model_reply,
    rewrite_reply,
)

FEE_QUESTION = "¿Cuánto cuesta un retiro inmediato?"
FEE_TITLE = "Comisiones para Cuentas Personales"
MINUTE = 60.0

ClientFactory = Callable[[ChatModel], TestClient]


@pytest.fixture
def embeddings() -> CountingFakeEmbeddings:
    return CountingFakeEmbeddings()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def make_client(
    settings: Settings, engine: PGEngine, embeddings: CountingFakeEmbeddings, clock: FakeClock
) -> ClientFactory:
    """Ingested fake help center + an app whose OpenAI seams are replaced by fakes."""
    ingest(settings, embeddings, engine)
    embeddings.embedded_texts.clear()

    def factory(model: ChatModel) -> TestClient:
        app = create_app(settings=settings, engine=engine, clock=clock)
        app.dependency_overrides[get_chat_model] = lambda: model
        app.dependency_overrides[get_embeddings] = lambda: embeddings
        return TestClient(app)

    return factory


def fee_model() -> RecordingFakeChatModel:
    """Answers questions that each start a conversation (one model call per question)."""
    return RecordingFakeChatModel(responses=[model_reply("Cuesta 1,5% del monto.", ["NIM-020"])])


def conversation_model(exchanges: int) -> RecordingFakeChatModel:
    """Answers a first question, then follow-ups: rewrite, then generate, for each."""
    responses = [model_reply("Respuesta 1.", ["NIM-020"])]
    for n in range(2, exchanges + 1):
        responses += [rewrite_reply(f"Pregunta autónoma {n}"), model_reply(f"Respuesta {n}.", [])]
    return RecordingFakeChatModel(responses=responses)


def question(text: str, conversation_id: str | None = None) -> dict[str, str]:
    body = {"question": text}
    if conversation_id is not None:
        body["conversation_id"] = conversation_id
    return body


def start_conversation(client: TestClient, text: str) -> str:
    conversation_id: str = client.post("/api/chat", json=question(text)).json()["conversation_id"]
    return conversation_id


def call_text(call: list[BaseMessage]) -> str:
    return "\n".join(str(m.content) for m in call)


def test_chat_returns_answer_and_sources(make_client: ClientFactory) -> None:
    response = make_client(fee_model()).post("/api/chat", json={"question": FEE_QUESTION})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Cuesta 1,5% del monto."
    assert body["sources"] == [{"id": "NIM-020", "title": FEE_TITLE}]
    assert isinstance(body["conversation_id"], str)
    assert isinstance(body["expires_in_seconds"], int)


def test_chat_requests_are_independent(make_client: ClientFactory) -> None:
    model = fee_model()
    client = make_client(model)

    client.post("/api/chat", json=question("Primera pregunta sobre comisiones"))
    client.post("/api/chat", json=question("Segunda pregunta"))

    assert len(model.received) == 2  # no rewrite call for the second question
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


def test_chat_rejects_non_string_conversation_id(make_client: ClientFactory) -> None:
    response = make_client(fee_model()).post(
        "/api/chat", json={"question": "Hola", "conversation_id": 42}
    )

    assert response.status_code == 422


def test_chat_rejects_conversation_id_over_64_chars(make_client: ClientFactory) -> None:
    response = make_client(fee_model()).post("/api/chat", json=question("Hola", "a" * 65))

    assert response.status_code == 422


def test_chat_first_question_starts_conversation(make_client: ClientFactory) -> None:
    response = make_client(fee_model()).post("/api/chat", json=question(FEE_QUESTION))

    assert response.status_code == 200
    assert response.json()["conversation_id"]


def test_chat_follow_up_keeps_conversation_id(make_client: ClientFactory) -> None:
    client = make_client(conversation_model(2))
    conversation_id = start_conversation(client, FEE_QUESTION)

    response = client.post("/api/chat", json=question("¿y en Chile?", conversation_id))

    assert response.status_code == 200
    assert response.json()["conversation_id"] == conversation_id


def test_chat_new_conversations_get_different_ids(make_client: ClientFactory) -> None:
    client = make_client(fee_model())

    first = start_conversation(client, FEE_QUESTION)
    second = start_conversation(client, FEE_QUESTION)

    assert first != second


def test_chat_uses_only_six_most_recent_exchanges(make_client: ClientFactory) -> None:
    model = conversation_model(8)
    client = make_client(model)
    conversation_id = start_conversation(client, "Pregunta número 1")
    for n in range(2, 9):
        response = client.post("/api/chat", json=question(f"Pregunta número {n}", conversation_id))
        assert response.status_code == 200

    generation = call_text(model.received[-1])

    assert len(model.received[-1]) == 1 + 2 * 6 + 1  # system + 6 exchanges + this question
    for n in range(2, 9):
        assert f"Pregunta número {n}" in generation
    assert "Pregunta número 1" not in generation
    assert "Respuesta 1." not in generation


def test_chat_reports_expires_in_seconds(make_client: ClientFactory) -> None:
    response = make_client(fee_model()).post("/api/chat", json=question(FEE_QUESTION))

    assert response.json()["expires_in_seconds"] == 900


def test_chat_expired_conversation_returns_404(
    make_client: ClientFactory, embeddings: CountingFakeEmbeddings, clock: FakeClock
) -> None:
    model = conversation_model(2)
    client = make_client(model)
    conversation_id = start_conversation(client, FEE_QUESTION)
    embeddings.embedded_texts.clear()

    clock.now += 15 * MINUTE + 1
    response = client.post("/api/chat", json=question("¿y en Chile?", conversation_id))

    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)
    assert len(model.received) == 1
    assert embeddings.embedded_texts == []


def test_chat_unknown_conversation_returns_404(
    make_client: ClientFactory, embeddings: CountingFakeEmbeddings
) -> None:
    model = fee_model()

    response = make_client(model).post("/api/chat", json=question(FEE_QUESTION, "never-returned"))

    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)
    assert model.received == []
    assert embeddings.embedded_texts == []


def test_chat_activity_keeps_conversation_open(
    make_client: ClientFactory, clock: FakeClock
) -> None:
    client = make_client(conversation_model(3))
    conversation_id = start_conversation(client, FEE_QUESTION)

    clock.now += 14 * MINUTE
    assert (
        client.post("/api/chat", json=question("¿y en Chile?", conversation_id)).status_code == 200
    )
    clock.now += 14 * MINUTE
    response = client.post("/api/chat", json=question("¿y en México?", conversation_id))

    assert response.status_code == 200
    assert response.json()["conversation_id"] == conversation_id


def test_chat_failed_question_is_not_in_conversation(make_client: ClientFactory) -> None:
    model = FlakyChatModel(
        responses=[
            model_reply("Respuesta 1.", ["NIM-020"]),
            rewrite_reply("Pregunta autónoma fallida"),
            FAIL,
            rewrite_reply("Pregunta autónoma siguiente"),
            model_reply("Respuesta siguiente.", ["NIM-020"]),
        ]
    )
    client = make_client(model)
    conversation_id = start_conversation(client, FEE_QUESTION)
    assert (
        client.post("/api/chat", json=question("Pregunta fallida", conversation_id)).status_code
        == 503
    )

    response = client.post("/api/chat", json=question("Pregunta siguiente", conversation_id))

    assert response.status_code == 200
    generation = call_text(model.received[-1])
    assert FEE_QUESTION in generation
    assert "Pregunta siguiente" in generation
    assert "fallida" not in generation


def test_chat_failed_question_does_not_extend_conversation(
    make_client: ClientFactory, clock: FakeClock
) -> None:
    model = FlakyChatModel(
        responses=[model_reply("Respuesta 1.", ["NIM-020"]), rewrite_reply("Pregunta"), FAIL]
    )
    client = make_client(model)
    conversation_id = start_conversation(client, FEE_QUESTION)

    clock.now += 10 * MINUTE
    assert (
        client.post("/api/chat", json=question("¿y en Chile?", conversation_id)).status_code == 503
    )
    clock.now += 6 * MINUTE
    response = client.post("/api/chat", json=question("¿y en México?", conversation_id))

    assert response.status_code == 404


def test_chat_does_not_carry_sources_from_earlier_answers(make_client: ClientFactory) -> None:
    model = RecordingFakeChatModel(
        responses=[
            model_reply("Cuesta 1,5% del monto.", ["NIM-020"]),
            rewrite_reply("Pregunta autónoma"),
            model_reply("De nada.", []),
        ]
    )
    client = make_client(model)
    conversation_id = start_conversation(client, FEE_QUESTION)

    response = client.post("/api/chat", json=question("Gracias", conversation_id))

    assert response.json()["sources"] == []


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


def test_chat_follow_up_embeds_only_search_query(
    make_client: ClientFactory, embeddings: CountingFakeEmbeddings
) -> None:
    client = make_client(conversation_model(2))
    conversation_id = start_conversation(client, FEE_QUESTION)
    embeddings.embedded_texts.clear()

    client.post("/api/chat", json=question("¿y en Chile?", conversation_id))

    assert embeddings.embedded_texts == ["Pregunta autónoma 2"]
