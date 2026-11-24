"""Answer-quality evals on LangSmith: `python -m evals.run_evals` (run from backend/).

Calls the real OpenAI models (costs credits). Needs OPENAI_API_KEY, LANGSMITH_API_KEY,
DATABASE_URL and an ingested index. Runs three datasets, one experiment each: single
questions, conversations (earlier turns asked live, then the graded question), and small talk
(greetings, thanks and "what can you do", plus boundary messages that must still search).
Datasets are created on first run; to change their examples, delete the dataset in LangSmith
and run again; new examples (by name) are added.
"""

import argparse
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
SMALL_TALK_DATASET = "support-chat-small-talk"
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
    small_talk: bool = False,
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
            "small_talk": small_talk,
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
    # Compound questions for the chat model comparison (switch-chat-model-gpt-6-luna, 2026-11-07).
    # Four topics: more than max_searches=3 allows one search each.
    _example(
        "fee-timing-2fa-card-es",
        "¿Cuánto cuesta un retiro inmediato, cuánto tarda, cómo activo la verificación en dos "
        "pasos y cómo pido la Tarjeta Nimbo?",
        "Spanish",
        f"Gives the instant withdrawal fee ({FEE}), says an instant withdrawal arrives in "
        "minutes, gives the steps to turn on two-step verification (Perfil > Seguridad > "
        "Verificación en dos pasos), and says the Nimbo card needs Level 2 verification, with a "
        "virtual card at once and the physical one in 5 to 10 business days. Any part not covered "
        "is stated explicitly.",
        required=["NIM-020", "NIM-013", "NIM-004", "NIM-060"],
    ),
    _example(
        "2fa-and-account-recovery-en",
        "How do I turn on two-step verification, and what do I do if I can't log in to my account?",
        "English",
        "Gives the steps to turn on two-step verification and explains how to recover access to "
        "the account (password reset link; assisted recovery with an ID photo and a selfie if the "
        "email or phone is lost), both as described in the documents.",
        required=["NIM-004", "NIM-003"],
    ),
    _example(
        "withdrawal-minimum-two-countries-and-timing-es",
        "¿Cuál es el mínimo por retiro inmediato en Chile y en México, y cuánto tarda?",
        "Spanish",
        "Gives the instant withdrawal minimum for Chile (500 CLP) and México (10 MXN), each "
        "labeled, and says an instant withdrawal arrives in minutes.",
        required=["NIM-020", "NIM-013"],
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
    # Compound follow-up (switch-chat-model-gpt-6-luna, 2026-11-07).
    _conversation_example(
        "compound-follow-up-es",
        [FEE_QUESTION],
        "¿y cuánto tarda y cómo activo la verificación en dos pasos?",
        "Spanish",
        "Says an instant withdrawal arrives in minutes and gives the steps to turn on two-step "
        "verification (Perfil > Seguridad > Verificación en dos pasos).",
        required=["NIM-013", "NIM-004"],
    ),
]


THANKS_FEE = "Does not state any fee, minimum or other fact about Nimbo."
SMALL_TALK_REPLY = (
    "A short reply in the question's language that does not say the help center lacks "
    "information, and states no facts about Nimbo."
)
CAPABILITIES = (
    "Says the chat answers questions about Nimbo using its help center and cannot see the "
    "visitor's account, and states no facts about Nimbo's products, fees or policies."
)
EN_FEE_QUESTION = "How much does an instant withdrawal cost?"
# Small talk (searches must be skipped) and boundary messages (must search), specified by the
# "Small talk" requirement of support-chat-api (small-talk-without-search, 2026-11-09).
SMALL_TALK_EXAMPLES = [
    _conversation_example(
        "greeting-es",
        [],
        "Hola",
        "Spanish",
        f"Greets the visitor. {SMALL_TALK_REPLY}",
        small_talk=True,
    ),
    _conversation_example(
        "greeting-en",
        [],
        "Hi there!",
        "English",
        f"Greets the visitor. {SMALL_TALK_REPLY}",
        small_talk=True,
    ),
    _conversation_example(
        "greeting-good-morning-es",
        [],
        "Buen día",
        "Spanish",
        f"Greets the visitor. {SMALL_TALK_REPLY}",
        small_talk=True,
    ),
    _conversation_example(
        "capabilities-es", [], "¿Qué podés hacer?", "Spanish", CAPABILITIES, small_talk=True
    ),
    _conversation_example(
        "capabilities-en",
        [],
        "What can you help me with?",
        "English",
        CAPABILITIES,
        small_talk=True,
    ),
    _conversation_example(
        "thanks-after-answer-es",
        [FEE_QUESTION],
        "¡Gracias!",
        "Spanish",
        f"Acknowledges the thanks. {SMALL_TALK_REPLY} {THANKS_FEE}",
        small_talk=True,
    ),
    _conversation_example(
        "thanks-after-answer-en",
        [EN_FEE_QUESTION],
        "Thanks, that helps.",
        "English",
        f"Acknowledges the thanks. {SMALL_TALK_REPLY} {THANKS_FEE}",
        small_talk=True,
    ),
    _conversation_example(
        "farewell-es",
        [FEE_QUESTION],
        "Listo, chau",
        "Spanish",
        f"Says goodbye. {SMALL_TALK_REPLY} {THANKS_FEE}",
        small_talk=True,
    ),
    _conversation_example(
        "greeting-with-question-es",
        [],
        "Hola, ¿cuánto cuesta un retiro inmediato?",
        "Spanish",
        f"States the NIM-020 instant withdrawal fee: {FEE}.",
        required=["NIM-020"],
    ),
    _conversation_example(
        "greeting-with-question-en",
        [],
        "Hi! How do I turn on two-step verification?",
        "English",
        "Gives the steps to turn on two-step verification, as separate lines.",
        required=["NIM-004"],
    ),
    _conversation_example(
        "thanks-with-follow-up-es",
        ["¿Cuál es el mínimo por retiro inmediato?"],
        "Gracias, ¿y en Chile?",
        "Spanish",
        CHILE_MINIMUM,
        required=["NIM-020"],
    ),
    _conversation_example(
        "what-can-i-do-declined-payment-es",
        [],
        "¿Qué puedo hacer si me rechazan un pago?",
        "Spanish",
        "Gives the general reasons a payment can be declined, with what to do, as "
        "described in the documents.",
        required=["NIM-032"],
    ),
    _conversation_example(
        "what-can-i-do-business-account-es",
        [],
        "¿Qué puedo hacer con una Cuenta de Negocios?",
        "Spanish",
        "Describes what a Business Account allows, as described in the documents.",
        any_of=["NIM-050", "NIM-021"],
    ),
    # No document covers this question, so only `searched` and the judge grade it.
    _conversation_example(
        "can-you-see-my-account-es",
        [],
        "¿Podés ver mi cuenta?",
        "Spanish",
        "Says the chat cannot see the visitor's account.",
    ),
]


def sources(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    """Deterministic: expected source ids present (or none for no-information)."""
    ids = {s["id"] for s in outputs["sources"]}
    if reference_outputs["no_information"] or reference_outputs.get("small_talk"):
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
    if reference_outputs["no_information"] or reference_outputs.get("small_talk"):
        return {"results": []}
    return {"key": "searched", "score": bool(outputs["searches"])}


def skipped_search(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    """Small talk is answered without a search (scores small-talk examples only)."""
    if not reference_outputs.get("small_talk"):
        return {"results": []}
    return {"key": "skipped_search", "score": not outputs["searches"]}


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


# Calibrated against gpt-4.1-mini on 2026-11-24 (change switch-eval-judge-gpt-6-luna).
JUDGE_MODEL = "gpt-6-luna"
# None for non-reasoning models. gpt-6-luna defaults to `medium`, so it needs an explicit value.
JUDGE_REASONING_EFFORT: str | None = "none"


def _cited_documents_block(documents: list[dict[str, str]]) -> str:
    """The cited documents' text, in the agent's format; empty keeps the prompt as it was."""
    if not documents:
        return ""
    blocks = "\n\n".join(f'<document id="{d["id"]}">\n{d["text"]}\n</document>' for d in documents)
    return f"\nCited documents:\n{blocks}"


def make_judge(
    model: str, reasoning_effort: str | None, key_suffix: str = ""
) -> Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]]:
    """The LLM-as-judge evaluator; `key_suffix` keeps several judges' feedback apart."""

    def judge(
        inputs: dict[str, Any], outputs: dict[str, Any], reference_outputs: dict[str, Any]
    ) -> dict[str, Any]:
        # Chat Completions, as in get_chat_model: the binding the spike verified.
        judge_model = ChatOpenAI(
            model=model, reasoning_effort=reasoning_effort, use_responses_api=False
        ).with_structured_output(Verdict)
        verdict = judge_model.invoke(
            "You grade answers of a help-center chatbot for Nimbo, a fictional payments company.\n"
            + (f"Earlier questions: {inputs['turns']}\n" if inputs.get("turns") else "")
            + f"Question: {inputs['question']}\n"
            f"Expected language: {reference_outputs['language']}\n"
            f"Expectation: {reference_outputs['expectation']}\n"
            f"Answer:\n{outputs['answer']}\n"
            f"Cited sources: {outputs['sources']}"
            + _cited_documents_block(outputs.get("cited_documents") or [])
        )
        assert isinstance(verdict, Verdict)
        return {
            "results": [
                {
                    "key": key + key_suffix,
                    "score": getattr(verdict, key),
                    "comment": verdict.reasoning,
                }
                for key in (
                    "grounded",
                    "correct_language",
                    "voseo",
                    "plain_text",
                    "meets_expectation",
                )
                # Voseo only applies to Spanish answers.
                if key != "voseo" or reference_outputs["language"] == "Spanish"
            ]
        }

    return judge


def _run(
    client: Client,
    dataset_name: str,
    description: str,
    examples: list[dict[str, Any]],
    target: Callable[[dict[str, Any]], dict[str, Any]],
    metadata: dict[str, Any],
    prefix: str,
    repetitions: int,
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
        evaluators=[
            sources,
            no_forbidden_text,
            searched,
            skipped_search,
            search_count,
            make_judge(JUDGE_MODEL, JUDGE_REASONING_EFFORT),
        ],
        experiment_prefix=prefix,
        metadata=metadata,
        # Answers vary between runs; 3 repetitions (the default) keep differences above noise.
        num_repetitions=repetitions,
        # Each evaluator call would be its own billed trace; scores still land as feedback.
        disable_evaluator_tracing=True,
    )

    # Per-metric pass rate (mean for numeric metrics), plus each failure with its example name.
    print(f"== {dataset_name}")
    scores: dict[str, list[bool]] = {}
    numeric: dict[str, list[float]] = {}
    for row in results:
        name = row["example"].metadata.get("name") if row["example"].metadata else "?"
        for result in row["evaluation_results"].get("results", []):
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
    parser = argparse.ArgumentParser(description=__doc__)
    # Gates (searched, skipped_search, ...) only count from a full run: all datasets, 3 repetitions.
    parser.add_argument(
        "--dataset", action="append", choices=["answers", "conversations", "small-talk"]
    )
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    selected = set(args.dataset or ["answers", "conversations", "small-talk"])
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
        """The answer, plus the search queries and the cited documents' text (for the judge)."""
        answer = ask(graph, question, conversation_id, context).model_dump()
        state = graph.get_state({"configurable": {"thread_id": conversation_id}}).values
        # The text the agent read. A cited id without it raises (KeyError): `agent` only keeps
        # retrieved ids, and a gap would fail `grounded` for the wrong reason.
        texts = {d.metadata["id"]: d.page_content for d in state["documents"]}
        cited = [{"id": s["id"], "text": texts[s["id"]]} for s in answer["sources"]]
        return {**answer, "searches": state["searches"], "cited_documents": cited}

    def answer(inputs: dict[str, Any]) -> dict[str, Any]:
        # A new conversation per example: each question is answered on its own.
        return graded(inputs["question"], uuid.uuid4().hex)

    def converse(inputs: dict[str, Any]) -> dict[str, Any]:
        conversation_id = uuid.uuid4().hex
        for turn in inputs["turns"]:
            ask(graph, turn, conversation_id, context)
        return graded(inputs["question"], conversation_id)

    client = Client()
    metadata = {
        "models": {
            "chat": settings.chat_model,
            "chat_reasoning_effort": settings.chat_reasoning_effort,
            "embeddings": settings.embedding_model,
        },
        "judge": {"model": JUDGE_MODEL, "reasoning_effort": JUDGE_REASONING_EFFORT},
    }
    effort = f"-{settings.chat_reasoning_effort}" if settings.chat_reasoning_effort else ""
    prefix = (
        f"agentic-{settings.chat_model}{effort}-k{settings.retrieval_k}-s{settings.max_searches}"
    )
    if "answers" in selected:
        _run(
            client,
            DATASET,
            "Nimbo support chat answers",
            EXAMPLES,
            answer,
            metadata,
            prefix,
            args.repetitions,
        )
    if "conversations" in selected:
        _run(
            client,
            CONVERSATIONS_DATASET,
            "Nimbo support chat answers to follow-up questions",
            CONVERSATION_EXAMPLES,
            converse,
            metadata,
            f"{prefix}-conversations",
            args.repetitions,
        )
    if "small-talk" in selected:
        _run(
            client,
            SMALL_TALK_DATASET,
            "Nimbo support chat small talk and boundary messages",
            SMALL_TALK_EXAMPLES,
            converse,
            metadata,
            f"{prefix}-small-talk",
            args.repetitions,
        )


if __name__ == "__main__":
    main()
