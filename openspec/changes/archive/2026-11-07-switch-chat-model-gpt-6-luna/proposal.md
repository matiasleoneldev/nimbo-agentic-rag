# Proposal

## Why

The agent from `agentic-rag` was accepted with a measured correctness loss. On multi-topic questions it often writes one narrow search about the first topic and stops, so it misses a document. That change named the next step: first try a stronger chat model, changing only configuration and running the evals, and only then consider a question-splitting step. `gpt-6-luna` is OpenAI's newest efficient model. It is also cheaper per token than `gpt-4.1-mini`, so a quality gain would not cost more.

## What Changes

- The chat model changes from `gpt-4.1-mini` to `gpt-6-luna`, only if the evals pass the acceptance rule below. (Decided 2026-11-07.)
- `gpt-6-luna` is used **without reasoning** (`reasoning_effort: none`) on the Chat Completions API. OpenAI's model docs say that Chat Completions supports function calling with this model only when `reasoning_effort` is `none`, and the agent always binds the search tool. (Decided 2026-11-07.)
- Deferred to a possible later change (Decided 2026-11-07): `gpt-6-luna` with reasoning (`low` or higher) on the Responses API. It might plan searches for compound questions better, but it needs new checks of strict structured output with tools, streaming chunks and reasoning items between turns. This change measures only whether a stronger base model writes better searches.
- `backend/app.yaml` gains an optional reasoning effort for the chat model, sent only when it is set, so switching back to `gpt-4.1-mini` stays a configuration change. (Decided 2026-11-07.)
- The system prompt, `k=4` and `max_searches=3` stay as they are, so the eval comparison isolates the model. (Decided 2026-11-07.)
- A throwaway spike runs first. It repeats the `agentic-rag` binding checks with `gpt-6-luna` and adds a compound-question check. If the spike shows that the non-reasoning mode cannot do what the agent needs, this proposal and the design are revised before any code changes. (Decided 2026-11-07.)
- Evals (Decided 2026-11-07):
  - The datasets gain compound questions: one with four topics, more than `max_searches` allows one search each; one in English; one that asks for values in two countries; and a compound follow-up in the conversations dataset.
  - Because the datasets change, `gpt-4.1-mini` is re-run on the extended datasets before the switch, and that run is the baseline. The judge stays `gpt-4.1-mini`.
  - Experiment names include the reasoning effort when one is set (`agentic-gpt-6-luna-none-k4-s3`).
- Acceptance (Decided 2026-11-07, following the floor set by `agentic-rag` on 2026-11-06):
  - Non-negotiable: `grounded`, `no_forbidden_text` and `searched` stay at 100% on both datasets.
  - No metric may fall below the `gpt-4.1-mini` baseline on the extended datasets. A tie is accepted (Decided 2026-11-07): the same quality on a newer model, likely cheaper and faster, is a better starting point for later improvements.
  - No margin is fixed in advance (Decided 2026-11-07). Whether a difference of a few points is real or noise, in either direction, is the author's decision once the results are in, recorded with its date in design.md.
  - A latency loss is accepted and reported. A correctness loss is not.
  - If the rule is not met, `app.yaml` goes back to `gpt-4.1-mini`, and the new examples, the configuration option and the results stay. The next change then tries reasoning on the Responses API or a question-splitting step.
- Out of scope (Decided 2026-11-07): prompt changes, `k` or `max_searches` changes, the Responses API, new tools, and API or page contract changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. No requirement changes: the specs do not name the chat model, and the existing requirements already cover compound questions ("Help-center searches", "Partially covered questions", "Variants by country and account type"). The new eval examples measure those requirements. The change sets `skip_specs: true`.

## Impact

- `backend/app.yaml`: `models.chat`, plus an optional `models.chat_reasoning_effort`.
- `backend/nimbo/config.py` (`Settings`) and `backend/nimbo/api.py` (`get_chat_model`).
- `backend/evals/run_evals.py`: new examples and the experiment prefix.
- `backend/tests/test_config.py`: assert the new setting.
- `README.md`: the eval results and the current model.
- No new dependency: `langchain-openai` 1.6.7 already supports `reasoning_effort`. No API, page or database change.
- Cost per token, per OpenAI's pricing page: `gpt-6-luna` costs $0.10 input / $0.50 output per 1M tokens.
