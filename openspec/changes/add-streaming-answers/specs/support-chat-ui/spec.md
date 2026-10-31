# Spec Delta

## MODIFIED Requirements

### Requirement: Conversation display
Each sent question and its answer SHALL be shown on the page in the order they were asked, as plain text with line breaks preserved. The page MUST send questions to `POST /api/chat/stream` and show the answer text while it arrives; when the `done` event arrives, the answer shown MUST become the `done` event's `answer`, and the question is answered. Under each answer that has sources, the page MUST show each source's id and title as plain text, not as links. After a question is sent, the input MUST be cleared. Each question after the first MUST be sent with the `conversation_id` of the most recent answered question, unless the conversation has expired. Reloading the page MUST start with an empty conversation, and its first question MUST be sent without a conversation id.

#### Scenario: Answer with sources
- **WHEN** the API answers with sources NIM-020
- **THEN** the answer text is shown under its question, followed by "NIM-020" and its title, with no link

#### Scenario: Answer appears while it is written
- **WHEN** the API has sent the `delta` text "Te cobramos" and not yet the `done` event
- **THEN** "Te cobramos" is shown in the question's answer bubble, with no sources yet

#### Scenario: Done answer replaces the streamed text
- **WHEN** the `delta` texts read "Te cobramos 1,5&#37;." and the `done` event's `answer` is "Te cobramos 1,5%."
- **THEN** the answer bubble shows "Te cobramos 1,5%."

#### Scenario: Answer markup is not rendered
- **WHEN** an answer contains the text `<b>hola</b>`
- **THEN** the page shows the literal characters `<b>hola</b>`, not bold text

#### Scenario: Input clears after sending
- **WHEN** a question is sent
- **THEN** the input is empty and the suggested questions are hidden

#### Scenario: Follow-up continues the conversation
- **WHEN** the first question is answered with a `conversation_id` and the visitor sends a second question
- **THEN** the first question is sent without `conversation_id` and the second question is sent with the `conversation_id` of the first answer

#### Scenario: Reload starts a new conversation
- **WHEN** the visitor has an answered question, reloads the page and sends a question
- **THEN** the conversation shown is empty before sending, and the question is sent without `conversation_id`

### Requirement: Pending state
While a question is waiting for its first answer text, the page SHALL show, in that question's answer bubble, a loading indicator made of three dots that bounce slightly one after another. Until the question is answered or fails, the page MUST NOT send another question (send button disabled, Enter sends nothing), and the partial answer MUST be marked busy for assistive technology. The indicator MUST be a status that contains the loading text in the page language, visually hidden so that assistive technology announces it: "Buscando en el Centro de Ayuda…" in Spanish, "Searching the Help Center…" in English. When the visitor's system asks for reduced motion, the dots MUST NOT move.

#### Scenario: Three-dot indicator while pending
- **WHEN** a question is waiting for its answer
- **THEN** its answer bubble shows three animated dots, and a status with the text "Buscando en el Centro de Ayuda…" is present

#### Scenario: Dots bounce in sequence
- **WHEN** a question is waiting for its answer
- **THEN** each dot's bounce is offset in time from the previous dot's, from first to last, so the three dots never move together

#### Scenario: Indicator replaced by the answer
- **WHEN** the first answer text of the pending question arrives
- **THEN** the three-dot indicator is gone and the answer text is shown in its bubble

#### Scenario: Partial answer is busy
- **WHEN** part of the answer is shown and the `done` event has not arrived
- **THEN** the answer is marked busy for assistive technology, and it is no longer marked busy once the `done` event arrives

#### Scenario: English loading indicator
- **WHEN** the page is in English and a question is waiting for its answer
- **THEN** a status with the text "Searching the Help Center…" is present

#### Scenario: Reduced motion
- **WHEN** the visitor's system asks for reduced motion and a question is waiting for its answer
- **THEN** the three dots are shown without animation

#### Scenario: No double send
- **WHEN** an answer is pending and the visitor presses Enter with a new question or clicks the send button
- **THEN** no new request is sent

#### Scenario: No send while the answer is being written
- **WHEN** part of the answer is shown, the `done` event has not arrived, and the visitor presses Enter with a new question
- **THEN** no new request is sent

### Requirement: Error messages
When the API rejects a question or fails, the page SHALL show an error message in the page language in place of the answer, including any answer text already shown, and keep the page usable. A `429` response MUST show "Hiciste muchas preguntas seguidas. Esperá un momento y volvé a intentarlo." in Spanish and "You asked too many questions in a row. Wait a moment and try again." in English. A `404` response MUST show "La conversación expiró. Volvé a hacer tu pregunta." in Spanish and "The conversation expired. Ask your question again." in English, and the next question MUST be sent without a conversation id. Any other failure (including network errors, an `error` event, and a stream that ends without a `done` event) MUST show "No pudimos responder tu pregunta. Intentalo de nuevo más tarde." in Spanish and "We couldn't answer your question. Try again later." in English.

#### Scenario: Rate limited
- **WHEN** the API responds `429`
- **THEN** the rate-limit message is shown and the visitor can type a new question

#### Scenario: Server error
- **WHEN** the API responds `503` or the request fails
- **THEN** the generic error message is shown

#### Scenario: Error after part of the answer
- **WHEN** the API has sent `delta` text and then ends the stream with an `error` event
- **THEN** the partial answer text is gone, the generic error message is shown in its place, and the visitor can send a new question

#### Scenario: Stream ends without an answer
- **WHEN** the API has sent `delta` text and the stream ends without a `done` or `error` event
- **THEN** the partial answer text is gone and the generic error message is shown in its place

#### Scenario: Conversation not found
- **WHEN** the API responds `404` to a question sent with a `conversation_id`
- **THEN** the expired-conversation message is shown, and the next question is sent without `conversation_id`

#### Scenario: English error messages
- **WHEN** the page is in English and the API responds `429`, then `503`, then `404`
- **THEN** the English rate-limit message is shown, then the English generic error message, then the English expired-conversation message

### Requirement: Answer that arrives after the page expired the conversation
When a question sent with a `conversation_id` is still waiting for its answer as the conversation expires on the page, and the API then answers it, the page SHALL show the answer and continue the conversation with that answer's `conversation_id`, as for any answered question.

#### Scenario: Pending answer arrives after page expiry
- **WHEN** a question sent with a `conversation_id` is pending as the conversation expires on the page, and the API then answers it with a `done` event
- **THEN** the answer is shown, the expired notice is hidden, and the next question is sent with the `conversation_id` of that answer
