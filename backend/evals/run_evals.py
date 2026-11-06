"""Answer-quality evals on LangSmith: `python -m evals.run_evals` (run from backend/).

Calls the real OpenAI models (costs credits). Needs OPENAI_API_KEY, LANGSMITH_API_KEY,
DATABASE_URL and an ingested index. Runs two datasets, one experiment each: single
questions, and conversations (earlier turns asked live, then the graded question). Datasets are
created on first run; to change their examples, delete the dataset in LangSmith and run again;
new examples (by name) are added.
"""

import uuid
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_postgres import PGEngine, PGVectorStore
from langgraph.checkpoint.memory import InMemorySaver
from langsmith import Client
from pydantic import BaseModel, Field

from nimbo.api import get_chat_model, get_embeddings
from nimbo.chat import ChatContext, ask, build_graph
from nimbo.config import ENV_FILE, load_settings, require_env

DATASET = "support-chat-answers"
CONVERSATIONS_DATASET = "support-chat-conversations"
CARD = "4111 1111 1111 1111"


def _example(
    name: str,
    question: str,
    language: str,
    expectation: str,
    required: list[str] | None = None,
    any_of: list[str] | None = None,
    no_information: bool = False,
    must_not_contain: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "inputs": {"question": question},
        "outputs": {
            "language": language,
            "expectation": expectation,
            "required_source_ids": required or [],
            "any_source_ids": any_of or [],
            "no_information": no_information,
            "must_not_contain": must_not_contain or [],
        },
        "metadata": {"name": name},
    }


FEE = "1,5% of the amount, minimum 150 ARS / 10 MXN / 2.500 COP / 500 CLP by country"
EXAMPLES = [
    _example(
        "fee-instant-withdrawal-es",
        "¿Cuánto cuesta un retiro inmediato a mi cuenta bancaria?",
        "Spanish",
        f"States the NIM-020 instant withdrawal fee: {FEE}.",
        required=["NIM-020"],
    ),
    _example(
        "fee-instant-withdrawal-en",
        "How much does an instant withdrawal to my bank account cost?",
        "English",
        f"States the NIM-020 instant withdrawal fee: {FEE}.",
        required=["NIM-020"],
    ),
    _example(
        "2fa-steps-es",
        "¿Cómo activo la verificación en dos pasos?",
        "Spanish",
        "Gives the steps to turn on two-step verification, as separate lines.",
        required=["NIM-004"],
    ),
    _example(
        "out-of-scope-capital",
        "¿Cuál es la capital de Australia?",
        "Spanish",
        "Says the help center has no information about it, without answering it and without "
        "pointing to any contact channel.",
        no_information=True,
    ),
    _example(
        "seller-did-not-ship-es",
        "¿Qué hago si un vendedor no me envió lo que compré?",
        "Spanish",
        "Explains what to do when a purchase never arrived (contact the seller, then open a "
        "dispute / buyer protection), as described in the documents.",
        any_of=["NIM-041", "NIM-042"],
    ),
    _example(
        "money-on-hold-es",
        "¿Por qué mi dinero está retenido?",
        "Spanish",
        "Explains the reasons money can be held, as described in the documents.",
        required=["NIM-015"],
    ),
    _example(
        "withdrawal-minimum-all-countries-es",
        "¿Cuál es el mínimo por retiro inmediato?",
        "Spanish",
        "Gives the minimum for Argentina (150 ARS), México (10 MXN), Colombia (2.500 COP) and "
        "Chile (500 CLP), each labeled.",
        required=["NIM-020"],
    ),
    _example(
        "withdrawal-minimum-chile-es",
        "¿Cuál es el mínimo por retiro inmediato en Chile?",
        "Spanish",
        "Gives the Chile minimum: 500 CLP.",
        required=["NIM-020"],
    ),
    _example(
        "mixed-partial-question-es",
        "¿Cuánto cuesta un retiro inmediato y cuál es la capital de Australia?",
        "Spanish",
        f"Gives the instant withdrawal fee ({FEE}) and says explicitly that the help center has "
        "no information about the capital of Australia.",
        required=["NIM-020"],
    ),
    _example(
        "declined-payment-my-account-es",
        "¿Por qué rechazaron mi pago de ayer?",
        "Spanish",
        "Says the chat cannot see the visitor's account, then gives the general reasons a "
        "payment can be declined.",
        required=["NIM-032"],
    ),
    _example(
        "card-number-in-question-es",
        f"Mi tarjeta {CARD} no funciona, ¿qué hago?",
        "Spanish",
        "Reminds the visitor not to share card data, and gives general help from the documents.",
        must_not_contain=[CARD, CARD.replace(" ", "")],
    ),
    # English suggested questions of the page (localize-chat-ui).
    _example(
        "2fa-steps-en",
        "How do I turn on two-step verification?",
        "English",
        "Gives the steps to turn on two-step verification, as separate lines.",
        required=["NIM-004"],
    ),
    _example(
        "seller-did-not-ship-en",
        "What do I do if a seller didn't send what I bought?",
        "English",
        "Explains what to do when a purchase never arrived (contact the seller, then open a "
        "dispute / buyer protection), as described in the documents.",
        any_of=["NIM-041", "NIM-042"],
    ),
    _example(
        "money-on-hold-en",
        "Why is my money on hold?",
        "English",
        "Explains the reasons money can be held, as described in the documents.",
        required=["NIM-015"],
    ),
    # English regressions found in the end-to-end check (2026-10-14).
    _example(
        "receive-money-fee-en",
        "Is there a fee to receive money?",
        "English",
        "Says receiving money is free.",
        required=["NIM-020"],
    ),
    _example(
        "close-account-with-balance-en",
        "Can I close my Nimbo account if I still have money in it?",
        "English",
        "Says the balance must be zero first (withdraw or spend it) before closing the account.",
        required=["NIM-005"],
    ),
    # Compound questions that need two documents (agentic-rag, 2026-11-06).
    _example(
        "fee-and-timing-instant-withdrawal-es",
        "¿Cuánto cuesta un retiro inmediato y cuánto tarda?",
        "Spanish",
        f"Gives the NIM-020 instant withdrawal fee ({FEE}) and the instant withdrawal timing "
        "from NIM-013 (minutes).",
        required=["NIM-020", "NIM-013"],
    ),
    _example(
        "2fa-and-account-recovery-es",
        "¿Cómo activo la verificación en dos pasos y qué hago si no puedo ingresar a mi cuenta?",
        "Spanish",
        "Gives the steps to turn on two-step verification and explains how to recover access to "
        "the account, both as described in the documents.",
        required=["NIM-004", "NIM-003"],
    ),
    _example(
        "card-request-and-declined-payment-es",
        "¿Cómo pido la Tarjeta Nimbo y qué hago si me rechazan un pago?",
        "Spanish",
        "Explains how to request the Nimbo card and the general reasons a payment can be "
        "declined with what to do, both as described in the documents.",
        required=["NIM-060", "NIM-032"],
    ),
    # Hard questions: three topics far apart in the corpus (agentic-rag, 2026-11-06).
    _example(
        "send-abroad-limit-dispute-es",
        "¿Cuánto me cobran por enviar dinero a otro país, cuánto puedo enviar por mes y cómo abro "
        "una disputa si tengo un problema con una compra?",
        "Spanish",
        "Gives the international send fee (2,5% of the amount, plus a 3,5% currency conversion "
        "margin), says the monthly sending limit depends on the verification level and the "
        "country (giving values from NIM-022), and explains how to open a dispute (Actividad, the "
        "payment, Informar un problema, within 180 days of the payment).",
        required=["NIM-020", "NIM-022", "NIM-041"],
    ),
    _example(
        "close-account-dispute-hold-es",
        "Quiero cerrar mi cuenta, pero tengo dinero retenido de una venta que tiene una disputa "
        "abierta. ¿Puedo cerrarla ya y cuándo se libera ese dinero?",
        "Spanish",
        "Says the account cannot be closed while it has an open dispute or held money, and that "
        "money from a payment with an open dispute stays held until the dispute is resolved.",
        required=["NIM-005", "NIM-015"],
    ),
    _example(
        "verify-2fa-card-es",
        "¿Cómo verifico mi identidad, cómo activo la verificación en dos pasos y cómo consigo la "
        "Tarjeta Nimbo?",
        "Spanish",
        "Explains how to verify identity (Perfil > Verificación; Level 2 needs the ID document "
        "and a selfie), the steps to turn on two-step verification (Perfil > Seguridad), and "
        "that the Nimbo card needs Level 2 verification, with a virtual card at once and the "
        "physical one in 5 to 10 business days.",
        required=["NIM-002", "NIM-004", "NIM-060"],
    ),
]


def _conversation_example(
    name: str, turns: list[str], question: str, language: str, expectation: str, **kwargs: Any
) -> dict[str, Any]:
    example = _example(name, question, language, expectation, **kwargs)
    example["inputs"]["turns"] = turns
    return example


FEE_QUESTION = "¿Cuánto cuesta un retiro inmediato?"
CHILE_MINIMUM = "Gives the Chile minimum for instant withdrawals: 500 CLP."
# Each example is named after the spec scenario it measures (add-conversation-memory).
CONVERSATION_EXAMPLES = [
    _conversation_example(
        "follow-up-country-es",
        ["¿Cuál es el mínimo por retiro inmediato?"],
        "¿y en Chile?",
        "Spanish",
        CHILE_MINIMUM,
        required=["NIM-020"],
    ),
    _conversation_example(
        "follow-up-timing-es",
        [FEE_QUESTION],
        "¿y cuánto tarda?",
        "Spanish",
        "Says how long an instant withdrawal takes (minutes).",
        required=["NIM-013"],
    ),
    _conversation_example(
        "comparison-standard-withdrawal-es",
        [FEE_QUESTION],
        "¿y es más caro que el retiro estándar?",
        "Spanish",
        f"Compares both fees: the instant withdrawal costs {FEE} and the standard withdrawal is "
        "free, so the instant one is more expensive.",
        required=["NIM-020"],
    ),
    _conversation_example(
        "comparison-business-account-es",
        [FEE_QUESTION],
        "¿y para una Cuenta de Negocios?",
        "Spanish",
        "Says withdrawals from a Business Account have the same conditions as from a Personal "
        "Account.",
        required=["NIM-021"],
    ),
    _conversation_example(
        "language-switch-en-es",
        ["How much does an instant withdrawal to my bank account cost?"],
        "¿y en Chile cuál es el mínimo?",
        "Spanish",
        CHILE_MINIMUM,
        required=["NIM-020"],
    ),
    _conversation_example(
        "card-number-earlier-turn-es",
        [f"Mi tarjeta {CARD} no funciona, ¿qué hago?"],
        "¿y si sigue sin funcionar?",
        "Spanish",
        "Gives general help from the documents for a card that still does not work.",
        must_not_contain=[CARD, CARD.replace(" ", "")],
    ),
    _conversation_example(
        "topic-change-es",
        [FEE_QUESTION],
        "¿Cómo activo la verificación en dos pasos?",
        "Spanish",
        "Gives the steps to turn on two-step verification, with nothing about withdrawals.",
        required=["NIM-004"],
    ),
    _conversation_example(
        "follow-up-out-of-scope-es",
        [FEE_QUESTION],
        "¿y cuál es la capital de Australia?",
        "Spanish",
        "Says the help center has no information about it, without answering it and without "
        "pointing to any contact channel.",
        no_information=True,
    ),
]


def sources(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    """Deterministic: expected source ids present (or none for no-information)."""
    ids = {s["id"] for s in outputs["sources"]}
    if reference_outputs["no_information"]:
        return {"key": "sources", "score": not ids}
    required = set(reference_outputs["required_source_ids"])
    any_of = set(reference_outputs["any_source_ids"])
    ok = required <= ids and (not any_of or bool(any_of & ids))
    return {"key": "sources", "score": ok}


def no_forbidden_text(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    leaked = any(text in outputs["answer"] for text in reference_outputs["must_not_contain"])
    return {"key": "no_forbidden_text", "score": not leaked}


def searched(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    """A question about Nimbo is answered from at least one search (not graded off-topic)."""
    if reference_outputs["no_information"]:
        return {"results": []}
    return {"key": "searched", "score": bool(outputs["searches"])}


def search_count(outputs: dict[str, Any]) -> dict[str, Any]:
    return {"key": "search_count", "score": len(outputs["searches"])}


NUMERIC_METRICS = {"search_count"}


class Verdict(BaseModel):
    reasoning: str
    grounded: bool = Field(
        description="No invented facts about Nimbo: only facts from the cited documents. "
        "An answer that only says the help center has no information is grounded."
    )
    correct_language: bool = Field(description="Answer is in the expected language.")
    voseo: bool = Field(
        description="False only if the answer uses tú-only forms (tienes, puedes, haz, eres) or "
        "usted forms (usted, tiene que). Voseo (tenés, podés, hacé) passes, and so do forms "
        "shared by voseo and tú such as the subjunctive (estés, puedas) and 'tu'/'te'."
    )
    plain_text: bool = Field(description="No Markdown or HTML markup.")
    meets_expectation: bool = Field(description="Satisfies the stated expectation.")


def judge(
    inputs: dict[str, Any], outputs: dict[str, Any], reference_outputs: dict[str, Any]
) -> dict[str, Any]:
    judge_model = ChatOpenAI(model="gpt-4.1-mini").with_structured_output(Verdict)
    verdict = judge_model.invoke(
        "You grade answers of a help-center chatbot for Nimbo, a fictional payments company.\n"
        + (f"Earlier questions: {inputs['turns']}\n" if inputs.get("turns") else "")
        + f"Question: {inputs['question']}\n"
        f"Expected language: {reference_outputs['language']}\n"
        f"Expectation: {reference_outputs['expectation']}\n"
        f"Answer:\n{outputs['answer']}\n"
        f"Cited sources: {outputs['sources']}"
    )
    assert isinstance(verdict, Verdict)
    return {
        "results": [
            {"key": key, "score": getattr(verdict, key), "comment": verdict.reasoning}
            for key in ("grounded", "correct_language", "voseo", "plain_text", "meets_expectation")
            # Voseo only applies to Spanish answers.
            if key != "voseo" or reference_outputs["language"] == "Spanish"
        ]
    }


def _run(
    client: Client,
    dataset_name: str,
    description: str,
    examples: list[dict[str, Any]],
    target: Callable[[dict[str, Any]], dict[str, Any]],
    metadata: dict[str, Any],
    prefix: str,
) -> None:
    if client.has_dataset(dataset_name=dataset_name):
        dataset = client.read_dataset(dataset_name=dataset_name)
    else:
        dataset = client.create_dataset(dataset_name, description=description)
    existing = {(e.metadata or {}).get("name") for e in client.list_examples(dataset_id=dataset.id)}
    missing = [e for e in examples if e["metadata"]["name"] not in existing]
    if missing:
        client.create_examples(dataset_id=dataset.id, examples=missing)

    results = client.evaluate(
        target,
        data=dataset_name,
        evaluators=[sources, no_forbidden_text, searched, search_count, judge],
        experiment_prefix=prefix,
        metadata=metadata,
        # Answers vary between runs; 3 repetitions keep pipeline vs agent differences above noise.
        num_repetitions=3,
    )

    # Per-metric pass rate (mean for numeric metrics), plus each failure with its example name.
    print(f"== {dataset_name}")
    scores: dict[str, list[bool]] = {}
    numeric: dict[str, list[float]] = {}
    for row in results:
        name = row["example"].metadata.get("name") if row["example"].metadata else "?"
        for result in row["evaluation_results"]["results"]:
            if result.key in NUMERIC_METRICS:
                numeric.setdefault(result.key, []).append(float(result.score or 0))
                continue
            passed = bool(result.score)
            scores.setdefault(result.key, []).append(passed)
            if not passed:
                print(f"FAIL {result.key}: {name} -- {result.comment or ''}")
    for key, values in scores.items():
        print(f"{key}: {sum(values)}/{len(values)}")
    for key, numbers in numeric.items():
        print(f"{key}: mean {sum(numbers) / len(numbers):.2f}")


def main() -> None:
    load_dotenv(ENV_FILE)
    settings = load_settings()
    engine = PGEngine.from_connection_string(url=require_env("DATABASE_URL"))
    store = PGVectorStore.create_sync(
        engine=engine, table_name=settings.table, embedding_service=get_embeddings(settings)
    )
    context = ChatContext(
        get_chat_model(settings),
        store,
        settings.retrieval_k,
        settings.max_exchanges,
        settings.max_searches,
    )
    graph = build_graph(InMemorySaver())

    def graded(question: str, conversation_id: str) -> dict[str, Any]:
        """The answer, plus the search queries of the graded question."""
        answer = ask(graph, question, conversation_id, context).model_dump()
        state = graph.get_state({"configurable": {"thread_id": conversation_id}}).values
        return {**answer, "searches": state["searches"]}

    def answer(inputs: dict[str, Any]) -> dict[str, Any]:
        # A new conversation per example: each question is answered on its own.
        return graded(inputs["question"], uuid.uuid4().hex)

    def converse(inputs: dict[str, Any]) -> dict[str, Any]:
        conversation_id = uuid.uuid4().hex
        for turn in inputs["turns"]:
            ask(graph, turn, conversation_id, context)
        return graded(inputs["question"], conversation_id)

    client = Client()
    metadata = {"models": {"chat": settings.chat_model, "embeddings": settings.embedding_model}}
    prefix = f"agentic-{settings.chat_model}-k{settings.retrieval_k}-s{settings.max_searches}"
    _run(
        client,
        DATASET,
        "Nimbo support chat answers",
        EXAMPLES,
        answer,
        metadata,
        prefix,
    )
    _run(
        client,
        CONVERSATIONS_DATASET,
        "Nimbo support chat answers to follow-up questions",
        CONVERSATION_EXAMPLES,
        converse,
        metadata,
        f"{prefix}-conversations",
    )


if __name__ == "__main__":
    main()
