# Tasks

Unless a task says otherwise, verify the backend tasks with `poetry run ruff format . ; poetry run ruff check . ; poetry run mypy . ; poetry run pytest` in `backend/`, with `docker compose up -d db` running. Tasks marked **manual** call the real OpenAI API and cost credits, and they never go into pytest.

This change has no spec deltas (`skip_specs: true`). The judge and the eval target are eval tooling, so no spec scenario traces to them.

## 1. Cited documents in the outputs and the judge prompt

- [x] 1.1 In `backend/evals/run_evals.py`, make `graded` add `cited_documents: [{id, text}]` from the state's `documents`, in `sources` order, raising if a cited id has no document (design.md, decisions 1 and 3). Make `make_judge` add the `Cited documents:` block only when `outputs.get("cited_documents")` is non-empty (decision 2). Verify with the full backend gate, and with `poetry run python -m evals.run_evals --dataset answers --repetitions 1` (**manual**): the root runs' outputs carry `cited_documents` with one entry per cited source, and the judge's comments refer to the documents' content.
- [x] 1.2 Update the judge line of the eval section in `README.md` (decision 5). Verify that it matches `make_judge`.

## 2. New baseline and comparison

- [x] 2.1 **Manual**: run `poetry run python -m evals.run_evals` (all datasets, 3 repetitions). Record the three experiment names and the per-metric pass rates under `## Results` in design.md, next to the last full run judged without the text (`agentic-gpt-6-luna-none-k4-s3-d0901026`, `-conversations-2d44876e` and `-small-talk-753e4ee9`). Verify that no judge call failed and that every root run has `cited_documents`.
- [x] 2.2 **Manual**: the throwaway comparison script of design.md, decision 4, on the three experiments of 2.1. Under `## Results`, record per metric the disagreement of `@no-text` and of `@text` against the stored verdict, and the judge's tokens per call with and without the text. Verify that the rows carry both suffixed key sets and that no traces were created.
- [x] 2.3 **Manual**: review every row in the CSV of 2.2, with each `grounded` failure checked against the cited documents' text. Mark each one as an agent defect or a judge miss. Record the counts, the agent defects (example and the unsupported claim) and the outcome, dated, under `## Results`. Verify that every reviewed row has a mark.
