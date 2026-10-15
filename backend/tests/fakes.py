"""Test doubles for the OpenAI-backed seams (tests never call OpenAI)."""

import json
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import BaseMessage
from openai import OpenAIError

VECTOR_SIZE = 16


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


class FailingChatModel(FakeListChatModel):
    """Simulates the model provider being down."""

    def _call(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> str:
        raise OpenAIError("provider unavailable")


def model_reply(answer: str, source_ids: list[str], has_information: bool = True) -> str:
    return json.dumps(
        {
            "question_language": "Spanish",
            "answer": answer,
            "source_ids": source_ids,
            "has_information": has_information,
        }
    )
