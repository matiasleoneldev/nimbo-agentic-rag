# Design

## Context

- [frontend/app/page.tsx](../../../frontend/app/page.tsx) is a single `"use client"` component with every text hard-coded in Spanish.
- [frontend/app/layout.tsx](../../../frontend/app/layout.tsx) hard-codes `<html lang="es">` and Spanish metadata.
- The page is currently static.
- The E2E tests in `frontend/e2e/chat.spec.ts` select elements by Spanish accessible names ("Tu pregunta", "Conversación", "Enviar"…).
- The Playwright config sets no locale, so Chromium sends its default `en-US`. That only works today because the page ignores the header.

See proposal.md for motivation and the decisions.

## Goals / Non-Goals

**Goals:**
- Choose the language once per request, on the server, so the first HTML is already in the right language: no flash of Spanish and a correct `lang` attribute.
- Two languages with a compile-time guarantee that neither one is missing a text.

**Non-Goals:**
- Locale-prefixed routes (`/es`, `/en`), SEO per language, or any third language.
- Locale-aware number or date formatting: the page formats neither.
- Switching language without a reload. Nothing on the page can change the language yet, so an entry's error message may keep the text it had when it was created.

## Decisions

### Read `Accept-Language` in server components; no proxy, no `[lang]` segment

The Next.js 16 i18n guide uses a `proxy` that redirects to `/[lang]`. That approach brings shareable per-language URLs, but this is a single page with no SEO goal. Instead:
- The root layout and the page call `headers()` and resolve the language themselves.
- The layout sets `<html lang>`.
- `generateMetadata` returns the localized title and description.
- The page renders the client component with that language's dictionary as a prop.

Reading headers makes the route dynamic, which is acceptable for a demo.

Alternative rejected: detecting on the client with `navigator.languages`. The server HTML would come out in Spanish and switch after hydration, and the `lang` attribute would be wrong for crawlers and screen readers at load time.

### Hand-rolled header parsing, no Negotiator / intl-localematcher

The rule only has to answer one question: is the primary subtag of the highest-priority tag `es`, `ca`, `gl` or `eu`? The steps are:
1. Split the header on commas.
2. Read each tag's `q` (default 1).
3. Drop `q=0`.
4. Take the tag with the highest `q`; on a tie, the earliest one wins.
5. Compare its primary subtag against `es`, `ca`, `gl` and `eu`, case-insensitively.

That is about ten lines, against two dependencies built for full locale negotiation. No new dependency is added.

### One `i18n.ts` module with typed dictionaries

- `frontend/app/i18n.ts` exports:
  - `Language = "es" | "en"`
  - an explicit `Dictionary` type: string fields plus `suggestions: readonly string[]`
  - `dictionaries: Record<Language, Dictionary>`
  - `getLanguage()`, which reads `headers()`
- A missing or extra key fails `tsc`.
- The Spanish strings move over verbatim.
- No i18n library: there are about 20 strings, no plurals and no interpolation, and there are no translators.

### Split page.tsx: server entry plus client component

- The chat code moves unchanged to `frontend/app/chat.tsx`, still `"use client"`.
- It takes `t: Dictionary` and reads texts from it.
- `page.tsx` becomes a small async server component that renders `<Chat t={dictionaries[await getLanguage()]} />`.
- Error entries keep storing the message string, taken from `t` at the time the error happens.

### E2E: pin default locale, override per test

- `playwright.config.ts` sets `locale: "es-AR"` in the shared `use`, so the existing Spanish tests keep passing unchanged.
- English tests use `test.use({ locale: "en-US" })`, which sets both `Accept-Language` and `navigator.language`.
- The cases with a raw header use `extraHTTPHeaders`:
  - `en-US,es;q=0.9`
  - a request with no header, through Playwright's standalone `request` fixture, asserting `lang="en"` and the English title in the returned HTML.

### Evals

- Add these examples to the `support-chat-answers` dataset, each with the same expected sources as its Spanish counterpart:
  - `2fa-steps-en`: NIM-004
  - `seller-did-not-ship-en`: any of NIM-041 or NIM-042
  - `money-on-hold-en`: NIM-015
- Their questions are the English suggestions, verbatim.

## Risks / Trade-offs

- [English suggested questions retrieve the wrong documents, because the search crosses languages] → Run the new evals before changing the UI; one passing run is enough. If one fails, reword that English suggestion, run its eval again, and update the spec to match.
- [Link previews and search crawlers usually send no `Accept-Language`, so they show the English title and description to every audience] → Accepted on 2026-10-19: English is the language most visitors of a portfolio demo can read.
- [Static rendering is lost] → Acceptable: the page already depends on the API at runtime, and rendering it is cheap.
- [A future CDN or cache serves the wrong language] → Not a risk while nothing caches the page. Revisit together with the deployment target, using `Vary: Accept-Language`.
