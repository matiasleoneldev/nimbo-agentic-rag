"""HTTP API: `uvicorn nimbo.api:create_app --factory` (run from backend/)."""

import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langchain_core.embeddings import Embeddings
from langchain_core.exceptions import OutputParserException
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_postgres import PGEngine, PGVectorStore
from langgraph.checkpoint.memory import InMemorySaver
from openai import OpenAIError
from pydantic import BaseModel, StringConstraints

from nimbo.chat import ChatAnswer, ChatContext, ChatModel, ask, build_graph
from nimbo.config import ENV_FILE, Settings, load_settings, require_env
from nimbo.conversations import ConversationRegistry
from nimbo.rate_limit import RateLimiter

logger = logging.getLogger(__name__)

CHAT_PATH = "/api/chat"
UNAVAILABLE = "The assistant is temporarily unavailable. Please try again later."
NOT_FOUND = "Conversation not found. Start a new conversation."


class ChatRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    conversation_id: Annotated[str, StringConstraints(max_length=64)] | None = None


class ChatResponse(ChatAnswer):
    conversation_id: str
    expires_in_seconds: int


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_chat_model(settings: Annotated[Settings, Depends(get_settings)]) -> ChatModel:
    # JSON mode guarantees a parseable object for PydanticOutputParser.
    return ChatOpenAI(model=settings.chat_model).bind(response_format={"type": "json_object"})


def get_embeddings(settings: Annotated[Settings, Depends(get_settings)]) -> Embeddings:
    return OpenAIEmbeddings(model=settings.embedding_model)


def create_app(
    settings: Settings | None = None,
    engine: PGEngine | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    if settings is None or engine is None:
        load_dotenv(ENV_FILE)
    app = FastAPI(title="Nimbo Help Center chat")
    app.state.settings = settings or load_settings()
    app.state.engine = engine or PGEngine.from_connection_string(url=require_env("DATABASE_URL"))
    rate_limiter = RateLimiter(clock=clock)
    # ponytail: conversations live in this process, so the API must run as a single process;
    # swap in PostgresSaver (langgraph-checkpoint-postgres) to share them across workers.
    checkpointer = InMemorySaver()
    graph = build_graph(checkpointer)
    conversations = ConversationRegistry(
        checkpointer, app.state.settings.conversation_ttl_seconds, clock
    )

    # Middleware, not a dependency: it must count requests whose body fails validation too.
    @app.middleware("http")
    async def rate_limit(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method == "POST" and request.url.path == CHAT_PATH:
            # ponytail: direct client IP; trust X-Forwarded-For once a deployment target exists.
            client_ip = request.client.host if request.client else "unknown"
            retry_after = rate_limiter.hit(client_ip)
            if retry_after is not None:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many questions. Please wait and try again."},
                    headers={"Retry-After": str(retry_after)},
                )
        return await call_next(request)

    # Added last so it wraps everything, including 429 responses.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
        allow_methods=["POST"],
        allow_headers=["Content-Type"],
    )

    @app.post(CHAT_PATH, response_model=ChatResponse)
    def chat(
        body: ChatRequest,
        settings: Annotated[Settings, Depends(get_settings)],
        model: Annotated[ChatModel, Depends(get_chat_model)],
        embeddings: Annotated[Embeddings, Depends(get_embeddings)],
    ) -> ChatResponse | JSONResponse:
        conversations.sweep()
        conversation_id = body.conversation_id
        if conversation_id is None:
            conversation_id = uuid.uuid4().hex
        elif not conversations.is_open(conversation_id):
            return JSONResponse(status_code=404, content={"detail": NOT_FOUND})
        try:
            store = PGVectorStore.create_sync(
                engine=app.state.engine, table_name=settings.table, embedding_service=embeddings
            )
            context = ChatContext(model, store, settings.retrieval_k, settings.max_exchanges)
            answer = ask(graph, body.question, conversation_id, context)
        except OpenAIError, OutputParserException:
            logger.exception("Answer generation failed")
            if body.conversation_id is None:
                # The client never got this id, and sweep() only sees touched ids.
                checkpointer.delete_thread(conversation_id)
            return JSONResponse(status_code=503, content={"detail": UNAVAILABLE})
        conversations.touch(conversation_id)
        return ChatResponse(
            **answer.model_dump(),
            conversation_id=conversation_id,
            expires_in_seconds=settings.conversation_ttl_seconds,
        )

    return app
