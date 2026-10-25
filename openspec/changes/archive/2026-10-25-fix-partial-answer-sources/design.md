# Design

## Context

`generate` in `backend/nimbo/chat.py` parses the model's JSON into `ModelAnswer` (`question_language`, `answer`, `source_ids`, `has_information`). When `has_information` is false, every source is dropped. That rule exists because models often list the retrieved documents even when they answer "no information". The `add-chatbot` design added it on purpose, and `test_chat_no_information_returns_empty_sources` covers it.

The system prompt sets `has_information` to false only when the documents contain the information "at all". The partial-answer rule says nothing about the flag. In the failing runs the model lists `NIM-013` and `NIM-020` in `source_ids` and then sets `has_information` to false, so it contradicts itself, and the flag wins. See proposal.md (Why) for how often this happens.

## Goals / Non-Goals

**Goals:**
- Give partial answers their own value in the model output, so the model does not have to squeeze them into yes/no.
- Keep the guard that empties `sources` for no-information answers.

**Non-Goals:**
- Exposing coverage in the API response. The response body does not change.
- Any heuristic in code that second-guesses the model's coverage value, for example "keep the sources if ids were cited".
- Changes to retrieval, the rewrite step or the eval datasets.

## Decisions

- **Replace `has_information: bool` with `coverage: Literal["full", "partial", "none"]`.** The code only tests `coverage == "none"`. `full` and `partial` are separate values to make the model's choice clear, not because the code treats them differently.
  - Alternatives:
    - A renamed bool (`answered_any_part`). It needs a smaller diff, but it still asks the model a yes/no question about a three-way situation. The user chose the enum on 2026-10-25, so that one approach is measured per change.
    - Dropping the flag and trusting `source_ids`. This loses the guard against spurious sources on no-information answers.
- **`coverage` comes before `source_ids` in `ModelAnswer`.** `PydanticOutputParser` lists the fields in declaration order, and the model writes them in that order. The model then decides on coverage before it lists the documents, and the prompt rule "`source_ids` is empty when `coverage` is `none`" follows from a value it has already written. Today the model writes the flag last and can contradict the ids it has just written. `question_language` stays first, as decided in `add-chatbot`.
- **Each `coverage` value is tied to its own prompt rule.** The partial-answer rule ends with "and set coverage to partial". The no-information rule says "set coverage to none". The `source_ids` rule says "empty if coverage is none". The field gets no `Field(description=...)`. Every other `ModelAnswer` field is explained in the prompt, so this one follows the same style.
- **The fake keeps its shape.** `model_reply(answer, source_ids, coverage="full")` replaces the `has_information` parameter, with the same default meaning ("answered").

## Risks / Trade-offs

- [The model may still label a partial answer `none`.] → Re-run `mixed-partial-question-es` 5 times. Before this change it failed 2 times in 5. If it still fails, the README keeps the flaky note and a later change takes it up. It is not patched inside this change.
- [The model may label a no-information answer `partial` and leak spurious sources.] → `out-of-scope-capital` and `follow-up-out-of-scope-es` check that `sources` is empty. They are re-run in the same eval pass.
- [A `coverage` value outside the three allowed values fails parsing.] → This works the same way as any other malformed model output today. No new handling is needed.
