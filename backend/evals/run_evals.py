"""Answer-quality evals on LangSmith: `python -m evals.run_evals` (run from backend/).

Calls the real OpenAI models (costs credits). Needs OPENAI_API_KEY, LANGSMITH_API_KEY,
DATABASE_URL and an ingested index. The dataset is created on first run; to change its
examples, delete the dataset in LangSmith and run again; new examples (by name) are added.
"""

from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_postgres import PGEngine, PGVectorStore
from langsmith import Client
from pydantic import BaseModel, Field

from nimbo.api import get_chat_model, get_embeddings
from nimbo.chat import answer_question
from nimbo.config import ENV_FILE, load_settings, require_env

DATASET = "support-chat-answers"
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
        f"Question: {inputs['question']}\n"
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


def main() -> None:
    load_dotenv(ENV_FILE)
    settings = load_settings()
    engine = PGEngine.from_connection_string(url=require_env("DATABASE_URL"))
    store = PGVectorStore.create_sync(
        engine=engine, table_name=settings.table, embedding_service=get_embeddings(settings)
    )
    model = get_chat_model(settings)

    def target(inputs: dict[str, Any]) -> dict[str, Any]:
        return answer_question(inputs["question"], store, model, settings.retrieval_k).model_dump()

    client = Client()
    if client.has_dataset(dataset_name=DATASET):
        dataset = client.read_dataset(dataset_name=DATASET)
    else:
        dataset = client.create_dataset(DATASET, description="Nimbo support chat answers")
    existing = {(e.metadata or {}).get("name") for e in client.list_examples(dataset_id=dataset.id)}
    missing = [e for e in EXAMPLES if e["metadata"]["name"] not in existing]
    if missing:
        client.create_examples(dataset_id=dataset.id, examples=missing)

    results = client.evaluate(
        target,
        data=DATASET,
        evaluators=[sources, no_forbidden_text, judge],
        experiment_prefix=settings.chat_model,
        metadata={"models": {"chat": settings.chat_model, "embeddings": settings.embedding_model}},
    )

    # Per-metric pass rate, plus each failure with its example name.
    scores: dict[str, list[bool]] = {}
    for row in results:
        name = row["example"].metadata.get("name") if row["example"].metadata else "?"
        for result in row["evaluation_results"]["results"]:
            passed = bool(result.score)
            scores.setdefault(result.key, []).append(passed)
            if not passed:
                print(f"FAIL {result.key}: {name} -- {result.comment or ''}")
    for key, values in scores.items():
        print(f"{key}: {sum(values)}/{len(values)}")


if __name__ == "__main__":
    main()
