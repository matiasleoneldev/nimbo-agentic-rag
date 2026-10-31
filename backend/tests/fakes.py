"""Test doubles for the OpenAI-backed seams (tests never call OpenAI)."""

import json
import threading
from collections.abc import Iterator
from typing import Any, Literal

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk
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


class RecordingFakeChatModel(FakeListChatModel):
    """Replies with canned JSON strings and records the messages it received."""

    received: list[list[BaseMessage]] = []

    def _call(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> str:
        self.received.append(messages)
        return super()._call(messages, stop, run_manager, **kwargs)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        # LangChain calls _stream instead of _call while the graph is streamed; one char per chunk.
        reply = self._call(messages, stop, run_manager, **kwargs)
        for i, char in enumerate(reply):
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=char, chunk_position="last" if i == len(reply) - 1 else None
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
        for char in head:
            yield ChatGenerationChunk(message=AIMessageChunk(content=char))
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
        head, paused, tail = self._call(messages, stop, run_manager, **kwargs).partition(PAUSE)
        for char in head:
            yield ChatGenerationChunk(message=AIMessageChunk(content=char))
        if paused:
            self.resume.wait(timeout=10)
        for char in tail:
            yield ChatGenerationChunk(message=AIMessageChunk(content=char))
        if paused:
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


def rewrite_reply(search_query: str) -> str:
    return json.dumps({"search_query": search_query})
