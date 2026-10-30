# Proposal

## Why

Once a conversation has started, the suggested questions keep showing below the input every time it is empty, competing with the conversation for attention. The pending answer is shown as a line of pulsing text that does not read as "the assistant is writing", so it is less clear that the question is being processed.

## What Changes

- Decision 2026-10-30: the suggested questions are shown only while the conversation on the page is empty and the input is empty. Once the first question is sent they stay hidden, whether the input is empty or not, until the page is reloaded. Expiry or a failed question does not bring them back.
- Decision 2026-10-30: while a question is waiting for its answer, its answer bubble shows three slightly bouncing dots instead of visible loading text. The loading text in the page language stays in the indicator, visually hidden, so assistive technology announces it. The dots stay still when the visitor asks for reduced motion.
- The "No double send" scenario no longer clicks a suggested question while pending, since none is shown then. It uses Enter and the send button instead.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `support-chat-ui`: Suggested questions (shown only while the conversation is empty), Conversation display (suggested questions hidden after sending), Pending state (three-dot bubble with accessible loading text).

## Impact

- `frontend/app/chat.tsx`: suggestions visibility condition and pending bubble markup.
- `frontend/e2e/chat.spec.ts`: updated and new Playwright tests.
- No API, backend or dependency changes; `frontend/app/i18n.ts` keeps its `loading` texts.
