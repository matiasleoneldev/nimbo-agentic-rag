# Tasks

## 1. Measure English suggestions first

- [x] 1.1 Add the eval examples `2fa-steps-en`, `seller-did-not-ship-en` and `money-on-hold-en` to `backend/evals/run_evals.py`. Use the English suggested questions verbatim and the same source expectations as the Spanish counterparts. Verify with `poetry run ruff check .` and `poetry run mypy .`.
- [x] 1.2 Run `poetry run python -m evals.run_evals` (costs OpenAI credits; ask the user first). Verify that all three new examples pass `sources`, `correct_language` and `meets_expectation` in one run. If one fails, reword that English suggested question, run its eval again, and update the question in the spec delta and in the eval example to match.

## 2. Localize the page

- [x] 2.1 Create `frontend/app/i18n.ts` with:
  - `Language`, `Dictionary`, `dictionaries` (Spanish strings copied verbatim except the new subtitle; English strings from the spec delta, plus placeholder "Type your question…", button "Send", loading "Searching the Help Center…", accessible names "Your question", "Conversation", "Sources", "Suggested questions", and metadata title and description)
  - `getLanguage()`: highest-`q` tag; primary subtag `es`, `ca`, `gl` or `eu` gives Spanish, anything else English

  Verify with `npm run typecheck`.
- [x] 2.2 Move the chat component to `frontend/app/chat.tsx` reading all texts from a `t: Dictionary` prop, and make `frontend/app/page.tsx` a server component rendering it with the request's dictionary. Verify with `npm run lint` and `npm run typecheck`.
- [x] 2.3 Make `frontend/app/layout.tsx` set `<html lang>` from `getLanguage()` and replace the static `metadata` with `generateMetadata`. Verify with `npm run typecheck`.
- [x] 2.4 Set `locale: "es-AR"` in the shared `use` of `frontend/playwright.config.ts`. Update only the subtitle that `"shows title and subtitle"` asserts, and verify that the existing `frontend/e2e/chat.spec.ts` passes with `npm run test:e2e`.

## 3. E2E coverage for language

Add a `test.describe("page language")` block in `frontend/e2e/chat.spec.ts`. Each scenario traces to a test by name. Verify that all of them pass with `npm run test:e2e`.

- [x] 3.1 Page language / Spanish browser → `"shows Spanish for es-AR browser"`: Spanish title, `html[lang="es"]`.
- [x] 3.2 Page language / Spanish browser from another region → `"shows Spanish for es-ES browser"`.
- [x] 3.3 Page language / Other language of Spain → `"shows Spanish for ca-ES, gl-ES and eu-ES browsers"` (one test looping over the three locales).
- [x] 3.4 Page language / English browser → `"shows English for en-US browser"`: English title, `html[lang="en"]`.
- [x] 3.5 Page language / Other browser language → `"shows English for pt-BR browser"`.
- [x] 3.6 Page language / Spanish is not the highest priority → `"shows English when Spanish is not first"` (`extraHTTPHeaders` set to `en-US,es;q=0.9`).
- [x] 3.7 Page language / No language preference → `"shows English without Accept-Language"`, using the standalone `request` fixture: HTML has `lang="en"` and "Nimbo Help Center".
- [x] 3.8 Content is not translated / Spanish source title in an English page → `"keeps source titles as returned in English page"`.
- [x] 3.9 Page header / English header → `"shows English title and subtitle"`.
- [x] 3.10 Suggested questions / English suggestions → `"shows English suggested questions in order"`.
- [x] 3.11 Sensitive data notice / English notice → `"shows English sensitive data notice"`.
- [x] 3.12 Fictional company notice / English footer notice → `"shows English fictional company footer"`.
- [x] 3.13 Error messages / English error messages → `"shows English error messages"` (route answers `429`, then `503`).

The scenarios that are not new keep tracing to their existing tests, which now run under `es-AR`.

## 4. Docs and integration check

- [x] 4.1 Update [README.md](../../../README.md) to say that the UI language follows the browser (Spanish for `es*`, otherwise English). Verify that the README states this.
- [x] 4.2 Run the full frontend gate: `npm run lint ; npm run typecheck ; npm run test:e2e`. Then open the page in a browser set to English and in one set to Spanish, and check that each loads without a flash of the other language.
