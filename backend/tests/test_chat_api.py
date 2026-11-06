import dataclasses
import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Protocol

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from langchain_core.messages import BaseMessage
from langchain_postgres import PGEngine
from starlette.types import ASGIApp

from nimbo.api import create_app, get_chat_model, get_embeddings
from nimbo.chat import ChatModel
from nimbo.config import Settings
from nimbo.ingest import ingest
from tests.conftest import indexed_documents
from tests.fakes import (
    FAIL,
    PAUSE,
    CountingFakeEmbeddings,
    FailingChatModel,
    FakeClock,
    FlakyChatModel,
    PausingChatModel,
    RecordingFakeChatModel,
    model_reply,
    search_call,
)

FEE_QUESTION = "¿Cuánto cuesta un retiro inmediato?"
FEE_TITLE = "Comisiones para Cuentas Personales"
MINUTE = 60.0
UNAVAILABLE = "The assistant is temporarily unavailable. Please try again later."


class ClientFactory(Protocol):
    def __call__(self, model: ChatModel, **settings: Any) -> TestClient: ...


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

    def factory(model: ChatModel, **overrides: Any) -> TestClient:
        app = create_app(
            settings=dataclasses.replace(settings, **overrides), engine=engine, clock=clock
        )
        app.dependency_overrides[get_chat_model] = lambda: model
        app.dependency_overrides[get_embeddings] = lambda: embeddings
        return TestClient(app)

    return factory


def fee_model() -> RecordingFakeChatModel:
    """Answers questions that each start a conversation: one search, then the answer."""
    return RecordingFakeChatModel(
        responses=[search_call(FEE_QUESTION), model_reply("Cuesta 1,5% del monto.", ["NIM-020"])]
    )


def conversation_model(exchanges: int) -> RecordingFakeChatModel:
    """Answers a first question, then follow-ups: one search, then the answer, for each."""
    responses = [search_call("Pregunta autónoma 1"), model_reply("Respuesta 1.", ["NIM-020"])]
    for n in range(2, exchanges + 1):
        responses += [search_call(f"Pregunta autónoma {n}"), model_reply(f"Respuesta {n}.", [])]
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

    assert len(model.received) == 4  # a search turn and an answer turn per question
    second_call = model.received[2]
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

    # system + 6 exchanges + this question + this question's search call and its result
    assert len(model.received[-1]) == 1 + 2 * 6 + 1 + 2
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
    assert len(model.received) == 2
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
            search_call("Pregunta autónoma fallida"),
            FAIL,
            search_call("Pregunta autónoma siguiente"),
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
        responses=[model_reply("Respuesta 1.", ["NIM-020"]), search_call("Pregunta"), FAIL]
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
            search_call(FEE_QUESTION),
            model_reply("Cuesta 1,5% del monto.", ["NIM-020"]),
            # No search for this question: the earlier question's documents are not retrieved.
            model_reply("De nada.", ["NIM-020"]),
        ]
    )
    client = make_client(model)
    conversation_id = start_conversation(client, FEE_QUESTION)

    response = client.post("/api/chat", json=question("Gracias", conversation_id))

    assert response.json()["sources"] == []


def test_chat_sources_include_titles_without_duplicates(make_client: ClientFactory) -> None:
    model = RecordingFakeChatModel(
        responses=[
            search_call(FEE_QUESTION),
            model_reply("Respuesta.", ["NIM-020", "NIM-004", "NIM-020"]),
        ]
    )

    body = make_client(model).post("/api/chat", json={"question": FEE_QUESTION}).json()

    assert body["sources"] == [
        {"id": "NIM-020", "title": FEE_TITLE},
        {"id": "NIM-004", "title": "Activar la verificación en dos pasos"},
    ]


def test_chat_drops_unretrieved_source_ids(make_client: ClientFactory) -> None:
    model = RecordingFakeChatModel(
        responses=[search_call(FEE_QUESTION), model_reply("Respuesta.", ["NIM-020", "NIM-999"])]
    )

    body = make_client(model).post("/api/chat", json={"question": FEE_QUESTION}).json()

    assert [s["id"] for s in body["sources"]] == ["NIM-020"]


def test_chat_no_information_returns_empty_sources(make_client: ClientFactory) -> None:
    model = RecordingFakeChatModel(
        responses=[
            search_call("capital de Australia"),
            model_reply("El Centro de Ayuda no tiene esa información.", ["NIM-020"], "none"),
        ]
    )

    response = make_client(model).post("/api/chat", json={"question": "¿Capital de Australia?"})

    assert response.status_code == 200
    assert response.json()["sources"] == []


def test_chat_partial_answer_keeps_sources(make_client: ClientFactory) -> None:
    model = RecordingFakeChatModel(
        responses=[
            search_call(FEE_QUESTION),
            model_reply(
                "Cuesta 1,5% del monto. El Centro de Ayuda no tiene información sobre lo demás.",
                ["NIM-020"],
                "partial",
            ),
        ]
    )

    body = make_client(model).post("/api/chat", json={"question": FEE_QUESTION}).json()

    assert body["sources"] == [{"id": "NIM-020", "title": FEE_TITLE}]


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


def test_chat_embeds_each_search_query(
    make_client: ClientFactory, embeddings: CountingFakeEmbeddings
) -> None:
    model = RecordingFakeChatModel(
        responses=[
            search_call("comisión retiro inmediato"),
            search_call("tiempo retiro inmediato"),
            model_reply("Respuesta.", ["NIM-020"]),
        ]
    )

    make_client(model).post("/api/chat", json={"question": FEE_QUESTION})

    assert embeddings.embedded_texts == ["comisión retiro inmediato", "tiempo retiro inmediato"]


def test_chat_sources_from_every_search(
    make_client: ClientFactory, settings: Settings, engine: PGEngine
) -> None:
    # With k=1, a search for a document's own indexed text retrieves exactly that document.
    texts = {d.metadata["id"]: d.page_content for d in indexed_documents(settings, engine)}
    model = RecordingFakeChatModel(
        responses=[
            search_call(texts["NIM-020"]),
            search_call(texts["NIM-004"]),
            model_reply("Respuesta.", ["NIM-020", "NIM-004"]),
        ]
    )
    client = make_client(model, retrieval_k=1)

    body = client.post("/api/chat", json={"question": FEE_QUESTION}).json()

    assert [s["id"] for s in body["sources"]] == ["NIM-020", "NIM-004"]


def test_chat_stops_searching_at_limit(
    make_client: ClientFactory, embeddings: CountingFakeEmbeddings
) -> None:
    model = RecordingFakeChatModel(
        responses=[
            search_call("consulta 1"),
            search_call("consulta 2"),
            search_call("consulta 3", "consulta 4"),
            model_reply("Respuesta.", ["NIM-020"]),
        ]
    )

    response = make_client(model).post("/api/chat", json={"question": FEE_QUESTION})

    assert response.status_code == 200
    assert response.json()["sources"] == [{"id": "NIM-020", "title": FEE_TITLE}]
    assert embeddings.embedded_texts == ["consulta 1", "consulta 2", "consulta 3"]
    assert [b["tool_choice"] for b in model.bound] == ["required", None, None, "none"]


def test_chat_first_turn_must_search(make_client: ClientFactory) -> None:
    model = fee_model()

    make_client(model).post("/api/chat", json={"question": FEE_QUESTION})

    assert [b["tool_choice"] for b in model.bound] == ["required", None]


def test_chat_returns_503_when_model_searches_past_limit(make_client: ClientFactory) -> None:
    model = RecordingFakeChatModel(responses=[search_call(f"consulta {n}") for n in range(1, 5)])

    response = make_client(model).post("/api/chat", json={"question": FEE_QUESTION})

    assert response.status_code == 503
    assert response.json() == {"detail": UNAVAILABLE}


def test_chat_answer_without_search_has_no_sources(
    make_client: ClientFactory, embeddings: CountingFakeEmbeddings
) -> None:
    # OpenAI cannot skip the required first search; the fake ignores tool_choice, so this guards
    # the sources filter should a model answer anyway.
    model = RecordingFakeChatModel(responses=[model_reply("Respuesta.", ["NIM-020"])])

    response = make_client(model).post("/api/chat", json={"question": FEE_QUESTION})

    assert response.status_code == 200
    assert response.json()["sources"] == []
    assert embeddings.embedded_texts == []


def test_chat_conversation_holds_no_searches(make_client: ClientFactory) -> None:
    model = RecordingFakeChatModel(
        responses=[
            search_call("consulta de comisiones"),
            model_reply("Respuesta 1.", ["NIM-020"]),
            model_reply("Respuesta 2.", []),
        ]
    )
    client = make_client(model)
    conversation_id = start_conversation(client, FEE_QUESTION)

    client.post("/api/chat", json=question("¿y en Chile?", conversation_id))

    follow_up = model.received[-1]
    assert len(follow_up) == 4  # system + the earlier question and answer + this question
    assert FEE_QUESTION in call_text(follow_up)
    assert "Respuesta 1." in call_text(follow_up)
    assert "consulta de comisiones" not in str(follow_up)
    assert "<document" not in str(follow_up)


Event = tuple[str, dict[str, Any]]


def read_events(text: str) -> list[Event]:
    """Server-sent events as (event, data) pairs."""
    events = []
    for block in text.split("\n\n"):
        if block:
            fields = dict(line.split(": ", 1) for line in block.split("\n"))
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def ask_streaming(client: TestClient, body: dict[str, str]) -> list[Event]:
    response = client.post("/api/chat/stream", json=body)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return read_events(response.text)


def deltas(events: list[Event]) -> str:
    return "".join(data["text"] for name, data in events if name == "delta")


def stream_conversation(client: TestClient, text: str) -> str:
    name, data = ask_streaming(client, question(text))[-1]
    assert name == "done"
    conversation_id: str = data["conversation_id"]
    return conversation_id


def test_chat_stream_returns_deltas_then_done(make_client: ClientFactory) -> None:
    events = ask_streaming(make_client(fee_model()), question(FEE_QUESTION))

    names = [name for name, _ in events]
    assert names[-1] == "done"
    assert names[:-1] and set(names[:-1]) == {"delta"}


def test_chat_stream_rejects_blank_question(make_client: ClientFactory) -> None:
    response = make_client(fee_model()).post("/api/chat/stream", json={"question": "   "})

    assert response.status_code == 422
    assert "event:" not in response.text


def test_chat_stream_unknown_conversation_returns_404(
    make_client: ClientFactory, embeddings: CountingFakeEmbeddings
) -> None:
    model = fee_model()

    response = make_client(model).post(
        "/api/chat/stream", json=question(FEE_QUESTION, "never-returned")
    )

    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)
    assert model.received == []
    assert embeddings.embedded_texts == []


def test_chat_stream_follow_up_continues_conversation(make_client: ClientFactory) -> None:
    model = conversation_model(2)
    client = make_client(model)
    conversation_id = stream_conversation(client, FEE_QUESTION)

    name, data = ask_streaming(client, question("¿y en Chile?", conversation_id))[-1]

    assert name == "done"
    assert data["conversation_id"] == conversation_id
    generation = call_text(model.received[-1])
    assert FEE_QUESTION in generation
    assert "Respuesta 1." in generation


def test_chat_stream_deltas_join_to_answer(make_client: ClientFactory) -> None:
    model = RecordingFakeChatModel(
        responses=[search_call(FEE_QUESTION), model_reply("Te cobramos 1,5%.", ["NIM-020"])]
    )

    events = ask_streaming(make_client(model), question(FEE_QUESTION))

    assert deltas(events) == "Te cobramos 1,5%."
    assert events[-1][0] == "done"
    assert events[-1][1]["answer"] == "Te cobramos 1,5%."


def test_chat_stream_done_carries_sources_and_conversation(make_client: ClientFactory) -> None:
    name, data = ask_streaming(make_client(fee_model()), question(FEE_QUESTION))[-1]

    assert name == "done"
    assert data["answer"] == "Cuesta 1,5% del monto."
    assert data["sources"] == [{"id": "NIM-020", "title": FEE_TITLE}]
    assert isinstance(data["conversation_id"], str)
    assert data["expires_in_seconds"] == 900


def test_chat_stream_streams_only_answer_text(make_client: ClientFactory) -> None:
    client = make_client(conversation_model(2))
    conversation_id = stream_conversation(client, FEE_QUESTION)

    events = ask_streaming(client, question("¿y en Chile?", conversation_id))

    # Exactly the answer: no search query, language, coverage or source ids.
    assert deltas(events) == "Respuesta 2."
    assert "Pregunta autónoma" not in deltas(events)


def test_chat_stream_waits_for_parseable_reply_start(make_client: ClientFactory) -> None:
    # The real model's first chunk is empty; a leading newline is likewise unparseable alone.
    model = RecordingFakeChatModel(
        responses=[search_call(FEE_QUESTION), "\n" + model_reply("Te cobramos 1,5%.", ["NIM-020"])]
    )

    events = ask_streaming(make_client(model), question(FEE_QUESTION))

    assert deltas(events) == "Te cobramos 1,5%."
    assert events[-1][0] == "done"


def test_chat_stream_drops_unretrieved_source_ids(make_client: ClientFactory) -> None:
    model = RecordingFakeChatModel(
        responses=[search_call(FEE_QUESTION), model_reply("Respuesta.", ["NIM-020", "NIM-999"])]
    )

    _, data = ask_streaming(make_client(model), question(FEE_QUESTION))[-1]

    assert [s["id"] for s in data["sources"]] == ["NIM-020"]


@pytest.mark.parametrize("answer", ["Cuesta 1,5% del monto.", "Te cobramos 1,5&#37;."])
def test_chat_stream_done_matches_json_answer(make_client: ClientFactory, answer: str) -> None:
    reply = model_reply(answer, ["NIM-020", "NIM-999"])

    json_body = (
        make_client(RecordingFakeChatModel(responses=[search_call(FEE_QUESTION), reply]))
        .post("/api/chat", json=question(FEE_QUESTION))
        .json()
    )
    _, done = ask_streaming(
        make_client(RecordingFakeChatModel(responses=[search_call(FEE_QUESTION), reply])),
        question(FEE_QUESTION),
    )[-1]

    assert done["answer"] == json_body["answer"]
    assert done["sources"] == json_body["sources"]


def test_chat_rate_limit_is_shared_by_both_endpoints(make_client: ClientFactory) -> None:
    client = make_client(fee_model())

    statuses = [
        *[client.post("/api/chat", json=question(FEE_QUESTION)).status_code for _ in range(5)],
        *[
            client.post("/api/chat/stream", json=question(FEE_QUESTION)).status_code
            for _ in range(5)
        ],
    ]
    rejected = client.post("/api/chat/stream", json=question(FEE_QUESTION))

    assert statuses == [200] * 10
    assert rejected.status_code == 429
    assert int(rejected.headers["Retry-After"]) > 0
    assert "event:" not in rejected.text


def test_chat_stream_ends_with_error_when_model_fails(make_client: ClientFactory) -> None:
    events = ask_streaming(make_client(FailingChatModel(responses=[])), question(FEE_QUESTION))

    assert events == [("error", {"detail": UNAVAILABLE})]


def test_chat_stream_ends_with_error_after_partial_answer(make_client: ClientFactory) -> None:
    reply = model_reply("Te cobramos 1,5%.", ["NIM-020"])
    model = FlakyChatModel(
        responses=[search_call(FEE_QUESTION), reply[: reply.index("1,5")] + FAIL]
    )

    events = ask_streaming(make_client(model), question(FEE_QUESTION))

    assert deltas(events) == "Te cobramos "
    assert events[-1] == ("error", {"detail": UNAVAILABLE})
    assert "done" not in [name for name, _ in events]


def test_chat_stream_failed_question_is_not_in_conversation(make_client: ClientFactory) -> None:
    model = FlakyChatModel(
        responses=[
            model_reply("Respuesta 1.", ["NIM-020"]),
            search_call("Pregunta autónoma fallida"),
            FAIL,
            search_call("Pregunta autónoma siguiente"),
            model_reply("Respuesta siguiente.", ["NIM-020"]),
        ]
    )
    client = make_client(model)
    conversation_id = stream_conversation(client, FEE_QUESTION)
    assert ask_streaming(client, question("Pregunta fallida", conversation_id))[-1][0] == "error"

    events = ask_streaming(client, question("Pregunta siguiente", conversation_id))

    assert events[-1][0] == "done"
    generation = call_text(model.received[-1])
    assert FEE_QUESTION in generation
    assert "Pregunta siguiente" in generation
    assert "fallida" not in generation


def test_chat_stream_failed_first_question_leaves_no_conversation(
    make_client: ClientFactory,
) -> None:
    events = ask_streaming(make_client(FailingChatModel(responses=[])), question(FEE_QUESTION))

    assert all("conversation_id" not in data for _, data in events)


@contextmanager
def served(app: ASGIApp) -> Iterator[str]:
    """Runs the app on a real server: TestClient reads a whole stream before returning it."""
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run)
    thread.start()
    try:
        while not server.started:
            time.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join()


def cut_after_first_delta(url: str, model: PausingChatModel, body: dict[str, str]) -> None:
    """Disconnects while the answer is being written, then lets the cut generation finish."""
    with (
        httpx.Client(base_url=url) as http,
        http.stream("POST", "/api/chat/stream", json=body) as response,
    ):
        assert response.status_code == 200
        next(line for line in response.iter_lines() if line == "event: delta")
    model.resume.set()
    assert model.finished.wait(timeout=10)
    time.sleep(0.5)  # the cut run's own steps after the model call
    model.resume.clear()
    model.finished.clear()


def test_chat_stream_disconnect_leaves_question_out(
    make_client: ClientFactory, clock: FakeClock
) -> None:
    def cut_reply(answer: str) -> str:
        reply = model_reply(answer, ["NIM-020"])
        middle = reply.index(answer) + 4
        return reply[:middle] + PAUSE + reply[middle:]

    model = PausingChatModel(
        responses=[
            model_reply("Respuesta 1.", ["NIM-020"]),
            search_call("Pregunta autónoma cortada"),
            cut_reply("Respuesta cortada."),
            search_call("Pregunta autónoma siguiente"),
            model_reply("Respuesta siguiente.", ["NIM-020"]),
            search_call("Pregunta autónoma cortada otra vez"),
            cut_reply("Respuesta cortada otra vez."),
        ]
    )
    client = make_client(model)
    conversation_id = stream_conversation(client, FEE_QUESTION)

    with served(client.app) as url:
        cut_after_first_delta(url, model, question("Pregunta cortada", conversation_id))
        events = ask_streaming(client, question("Pregunta siguiente", conversation_id))

        assert events[-1][0] == "done"
        generation = call_text(model.received[-1])
        assert "Pregunta siguiente" in generation
        assert "cortada" not in generation

        clock.now += 10 * MINUTE
        cut_after_first_delta(url, model, question("Otra pregunta cortada", conversation_id))
        clock.now += 6 * MINUTE
        expired = client.post("/api/chat", json=question("¿Sigue abierta?", conversation_id))

    assert expired.status_code == 404
