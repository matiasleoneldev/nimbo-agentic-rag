# Tasks

Unless a task says otherwise, verify with `npm run lint ; npm run typecheck ; npm run test:e2e` in `frontend/`.

## 1. Suggested questions only on an empty conversation

- [x] 1.1 In `frontend/app/chat.tsx`, render the suggestions section only when `entries.length === 0 && input === ""`. Remove the suggestion buttons' `disabled={pending}`, since no suggestion is shown while a question is pending.
- [x] 1.2 Suggested questions / Suggestions hidden once the conversation has started → add `hides suggestions once the conversation has started` in `frontend/e2e/chat.spec.ts`: answer one question, then check that the input is empty and `suggestions(page)` has count 0.
- [x] 1.3 Suggested questions / Suggestions hidden after a failed question → add `hides suggestions after a failed question`: reply `503` and check that the generic error shows and `suggestions(page)` has count 0.
- [x] 1.4 Suggested questions / Suggestions return after reload → add `shows suggestions again after reload`: answer one question, reload, and check that `suggestions(page)` has count 4.
- [x] 1.5 Conversation display / Input clears after sending → in `clears input after sending`, change the expectation to `suggestions(page)` count 0.
- [x] 1.6 Suggested questions / Suggestions shown on empty input, English suggestions, Suggestions hidden while typing, Suggestions return when input is cleared → the existing tests `shows suggested questions in order below input`, `shows English suggested questions in order`, `hides suggestions while typing` and `shows suggestions again when input is cleared` pass unchanged.

## 2. Three-dot pending indicator

- [x] 2.1 In `frontend/app/chat.tsx`, replace the pending `<p role="status" className="animate-pulse ...">` with a `role="status"` element that holds `t.loading` in an `sr-only` span and three `aria-hidden` dots (`h-2 w-2 rounded-full bg-slate-400 motion-safe:animate-bounce`), staggered with `[animation-delay:-0.3s]` and `[animation-delay:-0.15s]` on the first two. While pending, the answer bubble is `w-fit`, so it is only as wide as the dots. Tailwind classes only, no new CSS or dependency.
- [x] 2.2 Pending state / Three-dot indicator while pending + Indicator replaced by the answer → add `shows a three-dot indicator while pending` in `frontend/e2e/chat.spec.ts`. Hold the response, then check that `getByRole("status")` has text "Buscando en el Centro de Ayuda…" and contains three dots with a running animation (computed `animation-name` is not `none`). Release the response, then check that the status is gone and the answer is visible.
- [x] 2.3 Pending state / English loading indicator → add `shows English loading indicator` in the `English page` describe, checking that `getByRole("status")` has text "Searching the Help Center…" while the response is held.
- [x] 2.4 Pending state / Reduced motion → add `does not animate the indicator with reduced motion`: call `page.emulateMedia({ reducedMotion: "reduce" })`, hold the response, and check that the dots' computed `animation-name` is `none`.
- [x] 2.6 Pending state / Dots bounce in sequence → the `[animation-delay:...]` classes from 2.1 never apply: Tailwind emits `motion-safe:animate-bounce` after arbitrary properties, and its `animation` shorthand resets the delay to `0s`, so the three dots bounce together. Set the delays with an inline `style={{ animationDelay }}` (`-0.3s`, `-0.15s`, `0s`) instead. Add `bounces the dots in sequence` in `frontend/e2e/chat.spec.ts`: hold the response and check that the dots' computed `animation-delay` values are `-0.3s`, `-0.15s`, `0s`, in that order.
- [x] 2.5 Pending state / No double send → in `does not send while an answer is pending`, drop the forced suggestion click and keep Enter with a second question. Add a forced click on the send button. Verify that only "Primera" is sent.

## 3. Integration

- [x] 3.1 Run the app (`npm run dev` plus the backend) and check in a browser: suggestions disappear after the first question and stay hidden with an empty input, the three dots bounce in the answer bubble while waiting, and they are replaced by the answer.

  Result 2026-10-30: checked with `npm run dev` and `/api/chat` mocked in the browser instead of the real backend, to avoid OpenAI calls (the page behavior does not depend on the answer content). All three behaviors confirmed; with `h-2` dots the bounce is about 2 px.
