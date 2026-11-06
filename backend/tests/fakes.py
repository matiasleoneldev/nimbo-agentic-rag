"""Test doubles for the OpenAI-backed seams (tests never call OpenAI)."""

import json
import threading
import uuid
from collections.abc import Callable, Iterator, Sequence
from typing import Any, Literal

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from openai import OpenAIError
from pydantic import ConfigDict, Field

VECTOR_SIZE = 16


class FakeClock:
    """Injectable clock that tests move forward by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class CountingFakeEmbeddings(DeterministicFakeEmbedding):
    """Deterministic fake embeddings that record every text they embed."""

    embedded_texts: list[str] = []

    def __init__(self) -> None:
        super().__init__(size=VECTOR_SIZE)
        self.embedded_texts = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.embedded_texts.extend(texts)
        return super().embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        self.embedded_texts.append(text)
        return super().embed_query(text)


SEARCH_KEY = "<search>"


def search_call(*queries: str) -> str:
    """A scripted reply that asks for one help-center search per query, all in one turn."""
    return json.dumps({SEARCH_KEY: list(queries)})


def _searches(reply: str) -> list[str] | None:
    try:
        parsed = json.loads(reply)
    except json.JSONDecodeError:
        return None
    return parsed.get(SEARCH_KEY) if isinstance(parsed, dict) else None


class RecordingFakeChatModel(FakeListChatModel):
    """Replies with canned strings and records the messages and the tool bindings it received.

    A `search_call` reply becomes an AIMessage with tool calls; any other string is the content.
    """

    received: list[list[BaseMessage]] = []
    bound: list[dict[str, Any]] = []

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        self.bound.append({"tool_choice": tool_choice, **kwargs})
        return self

    def _call(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> str:
        self.received.append(messages)
        return super()._call(messages, stop, run_manager, **kwargs)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        reply = self._call(messages, stop, run_manager, **kwargs)
        queries = _searches(reply)
        message = (
            AIMessage(content=reply)
            if queries is None
            else AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_help_center",
                        "args": {"query": q},
                        "id": f"call_{uuid.uuid4().hex}",
                        "type": "tool_call",
                    }
                    for q in queries
                ],
            )
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        # LangChain calls _stream instead of _generate while the graph is streamed.
        yield from _chunks(self._call(messages, stop, run_manager, **kwargs))


def _chunks(reply: str, last: bool = True) -> Iterator[ChatGenerationChunk]:
    """A search_call reply as one tool-call chunk; any other text one char per chunk."""
    queries = _searches(reply)
    if queries is not None:
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "name": "search_help_center",
                        "args": json.dumps({"query": q}),
                        "id": f"call_{uuid.uuid4().hex}",
                        "index": i,
                        "type": "tool_call_chunk",
                    }
                    for i, q in enumerate(queries)
                ],
                chunk_position="last",
            )
        )
        return
    for i, char in enumerate(reply):
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content=char, chunk_position="last" if last and i == len(reply) - 1 else None
            )
        )


FAIL = "<fail>"


class FlakyChatModel(RecordingFakeChatModel):
    """Like RecordingFakeChatModel, but raises the provider error where a response contains FAIL.

    When streamed, it first sends the text before FAIL, so `"<partial reply>" + FAIL` fails in
    the middle of an answer.
    """

    def _call(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> str:
        reply = super()._call(messages, stop, run_manager, **kwargs)
        if FAIL in reply:
            raise OpenAIError("provider unavailable")
        return reply

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        reply = RecordingFakeChatModel._call(self, messages, stop, run_manager, **kwargs)
        head, failed, _ = reply.partition(FAIL)
        yield from _chunks(head, last=not failed)
        if failed:
            raise OpenAIError("provider unavailable")


PAUSE = "<pause>"


class PausingChatModel(RecordingFakeChatModel):
    """When streamed, stops at PAUSE in a response until `resume` is set, then sends the rest.

    `finished` is set once a paused response has been sent to the end.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    resume: threading.Event = Field(default_factory=threading.Event)
    finished: threading.Event = Field(default_factory=threading.Event)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        reply = self._call(messages, stop, run_manager, **kwargs)
        head, paused, tail = reply.partition(PAUSE)
        if not paused:
            yield from _chunks(reply)
            return
        yield from _chunks(head, last=False)
        self.resume.wait(timeout=10)
        yield from _chunks(tail)
        self.finished.set()


class FailingChatModel(RecordingFakeChatModel):
    """Simulates the model provider being down."""

    def _call(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> str:
        raise OpenAIError("provider unavailable")


def model_reply(
    answer: str, source_ids: list[str], coverage: Literal["full", "partial", "none"] = "full"
) -> str:
    return json.dumps(
        {
            "question_language": "Spanish",
            "answer": answer,
            "coverage": coverage,
            "source_ids": source_ids,
        }
    )
