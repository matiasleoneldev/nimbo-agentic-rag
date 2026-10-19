# Proposal

## Why

The chat page is fixed in Spanish, but this is a public portfolio demo and many visitors (recruiters, reviewers) do not read Spanish. The API already answers in the language of the question, so the page's own texts are the only thing keeping non-Spanish speakers out.

## What Changes

- The page picks its language from the visitor's browser language preference (the `Accept-Language` request header), not from geographic location. (Decided 2026-10-19.)
- If the highest-priority browser language is Spanish or another language of Spain (`es`, `ca`, `gl`, `eu`, or any regional tag of them), the page is shown in Spanish. Any other language, `pt-BR` included, or no preference at all, shows the page in English. (Decided 2026-10-19.)
- English is the default even though link previews and search crawlers usually send no language preference, so they will show the English title and description. (Decided 2026-10-19.)
- The Spanish texts stay as they are today, in Rioplatense Spanish with voseo. They are not rewritten into neutral Latin American Spanish. (Decided 2026-10-19.)
- The one exception is the subtitle: in both languages it now names the region Nimbo serves (Argentina, Mexico, Colombia and Chile). (Decided 2026-10-19.)
- Every fixed text on the page gets an English version: header, suggested questions, sensitive data notice, footer, error messages, input placeholder, button, loading indicator, accessible names, and document title and description. (Decided 2026-10-19.)
- The English texts are neutral and formal, and they are accepted as written in the spec delta. (Decided 2026-10-19.)
- Product names are translated ("Nimbo Card", "Nimbo Help Center"), so that an English-only reader can understand them. (Decided 2026-10-19.)
- In English, the suggested questions are English questions, sent as typed. (Decided 2026-10-19.)
- Content the page does not author is never translated: the visitor's questions, the answers (the model writes them in the language of the question) and source titles (they come from the Spanish corpus). (Decided 2026-10-19.)
- The LangSmith eval dataset gains English versions of the three suggested questions that have no English example yet. The English suggestions must not be offered without measuring their answer quality first. One passing run is enough. If an example fails, its English suggested question is reworded, and the spec is updated to match. (Decided 2026-10-19.)
- Out of scope: a manual language selector and remembering the visitor's choice. They will come in a separate change later. (Decided 2026-10-19.)

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `support-chat-ui`:
  - New requirement: how the page language is chosen.
  - Changed requirements, each with a Spanish and an English text: page header (with a new Spanish subtitle), suggested questions, sensitive data notice, fictional company notice and error messages.

## Impact

- Frontend:
  - `frontend/app/layout.tsx` sets `<html lang>` and the metadata per request.
  - `frontend/app/page.tsx` is split into a server entry, which reads the language, and the existing client chat component.
  - New file for the dictionary of texts.
  - The page becomes dynamically rendered, because it reads request headers.
- E2E: the Playwright config pins the default locale to `es-AR` so the existing Spanish tests stay deterministic. New tests cover English and language selection.
- Evals: three new examples in `backend/evals/run_evals.py`.
- No backend API change. No new dependencies.
