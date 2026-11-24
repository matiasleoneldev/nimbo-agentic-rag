# Design

## Context

- `judge` (`backend/evals/run_evals.py`) builds `ChatOpenAI(model="gpt-4.1-mini").with_structured_output(Verdict)` on every call. `Verdict` puts a visible `reasoning` field before five booleans: `grounded`, `correct_language`, `voseo` (Spanish examples only), `plain_text` and `meets_expectation`. Each boolean becomes a feedback key, with `reasoning` as its comment.
- `_run` calls `client.evaluate` with `disable_evaluator_tracing=True` (since 2026-11-10), so judge calls send no LangSmith traces. A full run is 3 experiments: `<prefix>` (answers, 25 examples), `<prefix>-conversations` (9) and `<prefix>-small-talk` (14), each with 3 repetitions. That is 144 rows.
- The judge sees the question, the expected language, the expectation, the answer and the cited sources as `[id, title]` pairs. It never sees document text. That limit stays (proposal.md, out of scope).
- `gpt-6-luna`'s default reasoning effort is `medium`. The `switch-chat-model-gpt-6-luna` spike showed that Chat Completions accepts `reasoning_effort: "none"` with a strict `response_format` (check (e), 2026-11-07). The effort `low` without tools has not been tried in this repo.
- `langsmith` 0.14.4 accepts an experiment name or id in place of the target in `evaluate()`. It then runs only the evaluators on the stored runs' inputs and outputs (LangSmith docs, "Evaluate an existing experiment", read 2026-11-24).

## Goals / Non-Goals

**Goals:**
- Measure the `none` and `low` candidates against the stored `gpt-4.1-mini` verdicts on the same 144 rows, without running the agent.
- Leave the judge's model and effort as one place to change, and record them in every new experiment.

**Non-Goals:**
- A committed calibration command. Calibration is one-off and runs from a throwaway script.
- Making the judge configurable at run time (CLI flag or `app.yaml`).
- Recomputing or relabeling past experiments: the stored `gpt-4.1-mini` feedback stays as it is.

## Decisions

1. **`judge` becomes `make_judge(model, reasoning_effort, key_suffix="")`, which returns the evaluator.** Module constants `JUDGE_MODEL` and `JUDGE_REASONING_EFFORT` feed the evaluator passed to `_run`. The model is `ChatOpenAI(model=..., reasoning_effort=..., use_responses_api=False)`, the same binding as `get_chat_model`, so the judge stays on the API the spike verifies. The prompt and `Verdict` do not change. With an empty suffix, the feedback keys are unchanged (`grounded`, ...), so new experiments stay comparable by key with old ones. The calibration script passes a suffix.
   - Alternative: the judge model in `app.yaml`. Rejected, because `app.yaml` configures the running app and the judge is eval-only.
   - Alternative: a `--judge` CLI flag. Rejected, because only the one-off calibration needs another judge.

2. **For `gpt-6-luna`, the effort is always sent explicitly, `none` included.** Its default is `medium`, so leaving the effort unset would silently run `medium`. `gpt-4.1-mini` gets `reasoning_effort=None`, which is `ChatOpenAI`'s default and is not sent.

3. **A spike before any code change** (tasks.md, group 1). It is a throwaway script in the scratchpad, never committed, on 3 rows of the latest `agentic-gpt-6-luna-none-k4-s3` experiment. Checks:
   - (a) `ChatOpenAI(model="gpt-6-luna", reasoning_effort="low", use_responses_api=False).with_structured_output(Verdict)` returns a valid `Verdict` with no warning, and the request goes to `/v1/chat/completions` with `reasoning_effort: "low"`.
   - (b) The same holds with `reasoning_effort="none"`.
   - (c) Input, output and reasoning tokens per call for each effort, read from the raw message's `usage_metadata` (`include_raw=True`).
   - (d) `client.evaluate(<experiment>, evaluators=[...], disable_evaluator_tracing=True)` on an existing experiment adds feedback to the stored runs and creates no new traces (the project's trace count is unchanged afterwards).

   If (a), (b) or (d) fails, stop and revise proposal.md and this design before group 2. If only `low` fails, `none` is the only candidate.

4. **Calibration is a throwaway script** in the scratchpad that imports `make_judge` and `Client`. For each of the 3 experiments it runs `client.evaluate(<experiment>, evaluators=[...], disable_evaluator_tracing=True)` with three judges, each with its own key suffix:
   - `gpt-4.1-mini`, effort `None`, suffix `@gpt-4.1-mini` (the noise re-run),
   - `gpt-6-luna`, `none`, suffix `@gpt-6-luna-none`,
   - `gpt-6-luna`, `low`, suffix `@gpt-6-luna-low`.

   It then reads every row's feedback and writes one CSV for review to the scratchpad. The CSV has one line per row and metric where any judge differs from the stored, unsuffixed verdict: example name, repetition, metric, the four verdicts and the comments. Rows where any judge call failed are listed apart and left out of the counts.

5. **Disagreement is counted per row and metric.** Each metric's disagreement rate is the share of rows where a judge's verdict differs from the stored `gpt-4.1-mini` verdict. `voseo` only counts Spanish rows. The `@gpt-4.1-mini` re-run's rate is that metric's noise floor. A candidate within the floor on a metric is equivalent to `gpt-4.1-mini` on it. The manual review (proposal.md, Acceptance) covers every disagreement a candidate has, and the author adds the verdict "right: stored / candidate" to the CSV before the counts go into `## Calibration`.

6. **The experiment metadata gains `judge: {model, reasoning_effort}`** from the constants, next to `models`. The experiment prefix stays as it is: it names what is being measured (the agent), and the judge is how it is measured.

7. **The switch is the two constants.** If the calibration accepts a candidate, `JUDGE_MODEL` and `JUDGE_REASONING_EFFORT` change, and the README names the judge and the date of the switch. Pass rates from before that date were measured by `gpt-4.1-mini`.

## Risks / Trade-offs

- [Self-preference: `gpt-6-luna` grades its own answers and passes them too easily] → The acceptance rule rejects a candidate with any author-confirmed false pass on `grounded`. Over-lenient verdicts on other metrics also show up as disagreements the author reviews.
- [The calibration rows have few failures, so leniency has little room to show] → The stored verdicts include the known failures (`small-talk-without-search` voseo misses, `meets_expectation` on `greeting-with-question-en`), and the review covers both directions. This limit is reported with the results.
- [Three judges on one experiment measure agreement, not ground truth] → The author's review is the ground truth for disagreeing rows. Rows where all judges agree are not reviewed.
- [`low` costs more output tokens than its price per token suggests] → Spike check (c) and the calibration record tokens per call. The acceptance rule prefers `none` when it is as good.
- [`gpt-6-luna` has no dated snapshot, so the judge can drift] → Experiment metadata records the judge. A sudden shift in pass rates with an unchanged agent points at the judge. Not mitigated beyond that.
- [Re-evaluating an existing experiment might create traces or overwrite feedback] → Spike check (d) runs before the calibration. Suffixed keys never collide with the stored ones.
- [The calibration experiment is stale relative to the agent] → It does not matter: the judges grade the same stored outputs, which is what makes them comparable.

## Migration Plan

- Rollback: set `JUDGE_MODEL = "gpt-4.1-mini"` and `JUDGE_REASONING_EFFORT = None`, and revert the README line.
- The suffixed calibration feedback stays on the old experiments. It does not affect `run_evals`, which reads only the feedback of the experiments it creates.

## Spike findings

Task 1.1, 2026-11-24. `langchain-openai` 1.6.7, `langsmith` 0.14.4. Rows: `out-of-scope-capital`, `seller-did-not-ship-es` and `withdrawal-minimum-chile-es` of the answers experiment.

- (a) Pass. `ChatOpenAI(model="gpt-6-luna", reasoning_effort="low", use_responses_api=False)`: `_use_responses_api` is `False`, and the payload has `reasoning_effort: "low"` and no `reasoning` key. `with_structured_output(Verdict)` returned a valid `Verdict` on all 3 rows, with no parsing error and no warning.
- (b) Pass. The same with `reasoning_effort: "none"`: Chat Completions, valid `Verdict` on all 3 rows, no warning.
- (c) Tokens per call (input / output / of which reasoning): `low` 343/128/57, 614/212/106, 370/177/102; `none` 343/79/0, 614/113/0, 370/80/0. `low` roughly doubles the output tokens. Both efforts gave the same verdicts on the 3 rows, including `grounded: false` on `withdrawal-minimum-chile-es`. That row is reviewed in the calibration.
- (d) Pass. `evaluate("<experiment>", evaluators=[probe], disable_evaluator_tracing=True)` on the small-talk experiment added the probe's feedback to all 42 root runs. No run was created in the experiment's project, in `evaluators` or in the default project. The probe feedback was deleted afterwards (0 left).
- Calibration experiments (the latest with 3 repetitions of every example and no target errors):
  - answers: `agentic-gpt-6-luna-none-k4-s3-d0901026` (75 runs),
  - conversations: `agentic-gpt-6-luna-none-k4-s3-conversations-2d44876e` (27 runs),
  - small talk: `agentic-gpt-6-luna-none-k4-s3-small-talk-753e4ee9` (42 runs).
- Note: `Client.list_runs` warns that it is deprecated after 2027-01-31 (use `client.runs.query()`). `run_evals.py` does not call it.

## Calibration

Task 3.1, 2026-11-24. The three experiments of `## Spike findings`, 144 rows, three judges with suffixed keys, `max_concurrency=8`.

- No run was created in the three experiments' projects, in `evaluators` or in the default project. Every row carries all three suffixed key sets, and no judge call failed.
- `Client.list_feedback(run_ids=[...])` with all of an experiment's runs at once returned an incomplete set (207 keys looked missing). Querying one run at a time returned all of them. Only the throwaway script was affected.
- Tokens per call, mean over 144 calls (input / output / of which reasoning): `gpt-4.1-mini` 486 / 157 / 0; `gpt-6-luna` `none` 481 / 90 / 0; `gpt-6-luna` `low` 481 / 206 / 116.

Rows that differ from the stored `gpt-4.1-mini` verdict (`voseo` counts Spanish rows only):

| Metric | `@gpt-4.1-mini` (noise) | `none` | `low` |
|---|---|---|---|
| grounded | 0/144 | 29/144 | 23/144 |
| correct_language | 0/144 | 0/144 | 0/144 |
| voseo | 2/111 | 6/111 | 2/111 |
| plain_text | 0/144 | 3/144 | 14/144 |
| meets_expectation | 1/144 | 11/144 | 14/144 |

- `grounded`: every disagreement is a candidate failing a row that `gpt-4.1-mini` passed. Most of the candidates' comments say that only the source title is given, so the details cannot be verified. Some flag facts that are in the cited document, such as the 1,5% fee in `follow-up-country-es`. The two candidates disagree with each other on 36 of these rows (21 fail only with `none`, 15 only with `low`).
- `plain_text`: `low` fails 12 rows that the others pass. Its comments call hyphen or numbered lists Markdown.
- `voseo`: on 2 rows, the stored verdict fails and the re-run and both candidates pass. These are the known `gpt-4.1-mini` false negatives.
- `meets_expectation`: both candidates fail 11 rows the stored verdict passes, mostly steps given as one paragraph where the expectation asks for separate lines.

Paused 2026-11-24, before the review (task 3.2). The `grounded` disagreements come from the judge not seeing the cited documents' text: the candidates fail what they cannot verify, while `gpt-4.1-mini` passes on plausibility. Reviewing them now would measure the missing evidence, not the judges. The cited-document text for the judge moves ahead as its own change (decided 2026-11-24). The judge then reads the cited documents' text from the eval target's outputs. This change resumes with task 3.1a, which repeats the calibration on that change's first full experiments. The numbers above stay as the record of the judges without the document text.

### With the cited documents' text

Task 3.1a, 2026-11-24. The first full experiments of `judge-cited-document-text`, whose outputs carry the cited documents' text: `agentic-gpt-6-luna-none-k4-s3-bb70fb80` (75 runs), `-conversations-533917b2` (27) and `-small-talk-d821445b` (42, one target error left out, so 143 rows). The stored verdicts are `gpt-4.1-mini` with the text. No run was created, every row carries the three suffixed key sets, and no judge call failed.

| Metric | `@gpt-4.1-mini` (noise) | `none` | `low` |
|---|---|---|---|
| grounded | 0/143 | 2/143 | 9/143 |
| correct_language | 0/143 | 0/143 | 0/143 |
| voseo | 3/110 | 5/110 | 4/110 |
| plain_text | 0/143 | 4/143 | 12/143 |
| meets_expectation | 0/143 | 10/143 | 9/143 |

- With the text, the `grounded` disagreements fall from 29 to 2 (`none`) and from 23 to 9 (`low`).
- Tokens per call, mean over 144 calls (input / output / of which reasoning): `gpt-4.1-mini` 1,268 / 165 / 0; `none` 1,264 / 90 / 0; `low` 1,264 / 118 / 29.

Task 3.2, 2026-11-24. Every disagreement of a candidate (40 rows) was reviewed. `grounded` rows were checked against the cited documents' text.

- `plain_text`: rows with `•` bullets or `1.` numbered lines are plain text. The spec allows line breaks between steps or items, and neither is Markdown syntax that needs rendering (decided by the author, 2026-11-24). So `gpt-4.1-mini` is right on all 13 such rows: 4 failed by `none`, 12 by `low`.
- `meets_expectation`: on `2fa-steps-es`, `2fa-steps-en` and `greeting-with-question-en` (8 rows), the steps came in one paragraph where the expectation asks for separate lines. Both candidates are right. On `comparison-standard-withdrawal-es` (2 rows), the answer leaves out the minimums by country that the expectation lists, and `none` is right. On `card-number-earlier-turn-es` rep 3, the answer gives documented help ("contact the Help Center after 24 hours"), and `low` is wrong.
- `voseo`: on `follow-up-out-of-scope-es`, `farewell-es` and `thanks-after-answer-es` (3 rows), the stored verdict fails answers with no tú-only or usted forms. Both candidates are right. `none` is wrong on `withdrawal-minimum-all-countries-es` and `greeting-es` ("ayudarte" is a shared form). `low` is wrong on `follow-up-country-es`.
- `grounded`:
  - `can-you-see-my-account-es` and `capabilities-es` (4 rows), and the "No puedo ver tu cuenta" sentence in `card-number-in-question-es` and `money-on-hold-es` (3 rows): the candidates fail the chat's statement that it cannot see the account. That statement is about the chat, required by the system prompt, not a fact about Nimbo. These are judge misses: `low` on all 7, and `none` on 1.
  - `fee-and-timing-instant-withdrawal-es` rep 1: the answer says that the fee for Business accounts is not given. NIM-021 says Business withdrawals have the same conditions as Personal ones. Nothing is invented, so it is grounded, and `low` is wrong. The omission is an agent defect (completeness, not grounding), for a later change.
  - `verify-2fa-card-es` rep 2: "documento vigente" is supported by NIM-002 ("El documento está vencido" is a rejection reason). It is grounded, and `none` is wrong.
  - `verify-2fa-card-es` rep 3: "no indica los pasos para pedirla" is true of NIM-060. It is grounded, and `low` is wrong.
  - No row was marked not grounded, so neither candidate has a `grounded` false pass.

| Judge | Disagreements | Right | Wrong | `gpt-4.1-mini` wrong on the same rows |
|---|---|---|---|---|
| `none` | 21 | 13 | 8 | 13 |
| `low` | 34 | 11 | 23 | 11 |

Outcome (2026-11-24): **`gpt-6-luna` with `reasoning_effort: none` is accepted as the judge.**
- It has no `grounded` false pass, and it is wrong on 8 reviewed disagreements against 13 for `gpt-4.1-mini`. Its gains are the "separate lines" expectations, the minimums by country, and the known `voseo` false negatives.
- `low` is rejected: it is wrong on 23 against 11, mostly by counting bullets as Markdown and failing the chat's own "cannot see your account" statement.

### First run of the new judge

Task 5.1, 2026-11-24. Full run (3 datasets, 3 repetitions), judge `gpt-6-luna` with `reasoning_effort: none` and the cited documents' text. Experiments: `agentic-gpt-6-luna-none-k4-s3-817ba007`, `-conversations-26de6295` and `-small-talk-9fa0b632`. Each experiment's metadata names the judge. No target error, and no judge call failed. This run is the new judge's baseline, not a gate (proposal.md, Acceptance).

| Metric | answers | conversations | small talk |
|---|---|---|---|
| sources | 74/75 | 27/27 | 42/42 |
| no_forbidden_text | 75/75 | 27/27 | 42/42 |
| searched | 72/72 | 24/24 | 18/18 |
| skipped_search | - | - | 24/24 |
| search_count (mean) | 1.55 | 1.22 | 0.57 |
| grounded | 71/75 | 27/27 | 41/42 |
| correct_language | 75/75 | 27/27 | 42/42 |
| voseo | 54/54 | 27/27 | 29/30 |
| plain_text | 73/75 | 27/27 | 41/42 |
| meets_expectation | 64/75 | 26/27 | 39/42 |

Every failure was reviewed against the cited documents' text:

- Agent defects (13, for a later change):
  - Steps in one paragraph where the expectation asks for separate lines: `2fa-steps-es` ×2, `2fa-steps-en` ×3, `greeting-with-question-en` ×3. `gpt-4.1-mini` passed all of these.
  - The minimums by country are missing: `comparison-standard-withdrawal-es` ×1, and `withdrawal-minimum-two-countries-and-timing-es` ×1 (it also misses NIM-020, the `sources` failure).
  - The card's delivery time is missing in `fee-timing-2fa-card-es`. The monthly-limit cause is missing in `card-request-and-declined-payment-es` ×1.
- Judge misses (12):
  - `grounded` ×5. Three are omissions counted as invention: `2fa-and-account-recovery-es` ×2, and `card-request-and-declined-payment-es`, whose "the Help Center does not give the steps" is true of NIM-060. One is a translated app label in `2fa-and-account-recovery-en`. One is the chat's own "cannot see your account" in `can-you-see-my-account-es`.
  - `plain_text` ×3: answers with `•` lines or line breaks, which are plain text (decided 2026-11-24).
  - `voseo` ×1 (`thanks-with-follow-up-es`, no tú-only or usted forms).
  - `meets_expectation` ×3: details beyond the expectation required (`2fa-and-account-recovery-es`); the "limitation" sentence above, a second time (`card-request-and-declined-payment-es`); and `receive-money-fee-en`, where the answer correctly adds the Business fee and the expectation reads "free" with no qualification. That expectation is too narrow, a dataset fix for a later change.
- The new judge's most frequent miss is failing `grounded` on the chat's own "cannot see your account" statement, and on omissions. A `Verdict` wording that says both pass is a later change. The criteria were out of scope here.
