# support-chat-ui Specification

## Purpose

Defines the public web page visitors use to ask the Nimbo support chat questions: layout, suggested questions, input rules, how answers and sources are shown, error states and responsive behavior.

## Requirements

### Requirement: Page header
The page SHALL be publicly reachable without authentication and show a title and subtitle in the page language. In Spanish, the title is "Centro de Ayuda Nimbo" and the subtitle "Hacé tu pregunta sobre tu cuenta, pagos, comisiones o la Tarjeta Nimbo en Argentina, México, Colombia y Chile. Respondemos con la información del Centro de Ayuda." In English, the title is "Nimbo Help Center" and the subtitle "Ask about your account, payments, fees or the Nimbo Card in Argentina, Mexico, Colombia and Chile. We answer with information from the Help Center."

#### Scenario: Header is visible
- **WHEN** a visitor opens the page
- **THEN** the title and subtitle are visible, with no login prompt

#### Scenario: English header
- **WHEN** a visitor opens the page in English
- **THEN** the English title and subtitle are visible

### Requirement: Question input
The page SHALL offer a single-line text input for the question and a send button. The input MUST accept only typed or pasted text (no file, image or other attachments) and at most 500 characters. A question that is empty or whitespace-only MUST NOT be sent.

#### Scenario: Send with Enter
- **WHEN** the visitor types a question and presses Enter
- **THEN** the question is sent to the support chat API

#### Scenario: Blank question is not sent
- **WHEN** the input contains only whitespace and the visitor presses Enter or the send button
- **THEN** no request is sent

#### Scenario: Length cap
- **WHEN** the visitor types or pastes more than 500 characters
- **THEN** the input holds only the first 500 characters

### Requirement: Suggested questions
While the conversation is empty and the input is empty, the page SHALL show, below the input and stacked in a single column at every screen width, exactly four suggested questions in the page language, in this order. In Spanish: "¿Cuánto cuesta un retiro inmediato a mi cuenta bancaria?", "¿Cómo activo la verificación en dos pasos?", "¿Qué hago si un vendedor no me envió lo que compré?", "¿Por qué mi dinero está retenido?". In English: "How much does an instant withdrawal to my bank account cost?", "How do I turn on two-step verification?", "What do I do if a seller didn't send what I bought?", "Why is my money on hold?". While the input contains any character, the suggested questions MUST be hidden. Once a question has been sent, the suggested questions MUST stay hidden until the page is reloaded, whatever the input contains and whether that question was answered, failed or the conversation expired.

#### Scenario: Suggestions shown on empty input
- **WHEN** the page loads
- **THEN** the four suggested questions are visible below the input, in the specified order, one per row

#### Scenario: English suggestions
- **WHEN** the page loads in English
- **THEN** the four English suggested questions are visible, in the specified order

#### Scenario: Suggestions hidden while typing
- **WHEN** the visitor types any character in the input
- **THEN** the suggested questions are hidden

#### Scenario: Suggestions return when input is cleared
- **WHEN** no question has been sent and the visitor deletes all characters from the input
- **THEN** the suggested questions are visible again

#### Scenario: Suggestions hidden once the conversation has started
- **WHEN** a question has been answered and the input is empty
- **THEN** the suggested questions are hidden

#### Scenario: Suggestions hidden after a failed question
- **WHEN** the only question sent received `503` and the input is empty
- **THEN** the suggested questions are hidden

#### Scenario: Suggestions return after reload
- **WHEN** the visitor has an answered question and reloads the page
- **THEN** the four suggested questions are visible

### Requirement: Clicking a suggested question asks it
Clicking a suggested question SHALL put its text in the input and send it as the question, exactly as if the visitor had typed it and pressed send.

#### Scenario: Click sends the suggestion
- **WHEN** the visitor clicks "¿Por qué mi dinero está retenido?"
- **THEN** a request with that question is sent and the question appears in the conversation

### Requirement: Conversation display
Each sent question and its answer SHALL be shown on the page in the order they were asked, as plain text with line breaks preserved. Under each answer that has sources, the page MUST show each source's id and title as plain text, not as links. After a question is sent, the input MUST be cleared. Each question after the first MUST be sent with the `conversation_id` of the most recent answered question, unless the conversation has expired. Reloading the page MUST start with an empty conversation, and its first question MUST be sent without a conversation id.

#### Scenario: Answer with sources
- **WHEN** the API answers with sources NIM-020
- **THEN** the answer text is shown under its question, followed by "NIM-020" and its title, with no link

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

### Requirement: Sensitive data notice
The page SHALL show, next to the input and at all times, the sensitive data notice in the page language: in Spanish "No compartas contraseñas, códigos de verificación ni datos de tarjetas.", in English "Don't share passwords, verification codes or card details."

#### Scenario: Notice is visible
- **WHEN** a visitor opens the page
- **THEN** the sensitive data notice is visible near the input

#### Scenario: English notice
- **WHEN** a visitor opens the page in English
- **THEN** the English sensitive data notice is visible near the input

### Requirement: Fictional company notice
The page SHALL show, in its footer, the fictional company notice in the page language: in Spanish "Nimbo es una empresa ficticia. Este sitio es una demo con fines de portfolio.", in English "Nimbo is a fictional company. This site is a portfolio demo."

#### Scenario: Footer notice is visible
- **WHEN** a visitor opens the page and scrolls to the bottom
- **THEN** the fictional company notice is visible

#### Scenario: English footer notice
- **WHEN** a visitor opens the page in English and scrolls to the bottom
- **THEN** the English fictional company notice is visible

### Requirement: Pending state
While a question is waiting for its answer, the page SHALL show, in that question's answer bubble, a loading indicator made of three dots that bounce slightly one after another, and MUST NOT send another question (send button disabled, Enter sends nothing). The indicator MUST be a status that contains the loading text in the page language, visually hidden so that assistive technology announces it: "Buscando en el Centro de Ayuda…" in Spanish, "Searching the Help Center…" in English. When the visitor's system asks for reduced motion, the dots MUST NOT move.

#### Scenario: Three-dot indicator while pending
- **WHEN** a question is waiting for its answer
- **THEN** its answer bubble shows three animated dots, and a status with the text "Buscando en el Centro de Ayuda…" is present

#### Scenario: Dots bounce in sequence
- **WHEN** a question is waiting for its answer
- **THEN** each dot's bounce is offset in time from the previous dot's, from first to last, so the three dots never move together

#### Scenario: Indicator replaced by the answer
- **WHEN** the pending question is answered
- **THEN** the three-dot indicator is gone and the answer is shown in its bubble

#### Scenario: English loading indicator
- **WHEN** the page is in English and a question is waiting for its answer
- **THEN** a status with the text "Searching the Help Center…" is present

#### Scenario: Reduced motion
- **WHEN** the visitor's system asks for reduced motion and a question is waiting for its answer
- **THEN** the three dots are shown without animation

#### Scenario: No double send
- **WHEN** an answer is pending and the visitor presses Enter with a new question or clicks the send button
- **THEN** no new request is sent

### Requirement: Error messages
When the API rejects a question or fails, the page SHALL show an error message in the page language in place of the answer and keep the page usable. A `429` response MUST show "Hiciste muchas preguntas seguidas. Esperá un momento y volvé a intentarlo." in Spanish and "You asked too many questions in a row. Wait a moment and try again." in English. A `404` response MUST show "La conversación expiró. Volvé a hacer tu pregunta." in Spanish and "The conversation expired. Ask your question again." in English, and the next question MUST be sent without a conversation id. Any other failure (including network errors) MUST show "No pudimos responder tu pregunta. Intentalo de nuevo más tarde." in Spanish and "We couldn't answer your question. Try again later." in English.

#### Scenario: Rate limited
- **WHEN** the API responds `429`
- **THEN** the rate-limit message is shown and the visitor can type a new question

#### Scenario: Server error
- **WHEN** the API responds `503` or the request fails
- **THEN** the generic error message is shown

#### Scenario: Conversation not found
- **WHEN** the API responds `404` to a question sent with a `conversation_id`
- **THEN** the expired-conversation message is shown, and the next question is sent without `conversation_id`

#### Scenario: English error messages
- **WHEN** the page is in English and the API responds `429`, then `503`, then `404`
- **THEN** the English rate-limit message is shown, then the English generic error message, then the English expired-conversation message

### Requirement: Responsive layout
The page SHALL be usable from 320 px to 1920 px viewport width with no horizontal scrolling. On narrow viewports the input spans the available width; on wide viewports the content is centered with a bounded width.

#### Scenario: Phone width
- **WHEN** the page is shown at 375 px width
- **THEN** there is no horizontal scroll and the title, input and suggested questions are fully visible within the viewport width

#### Scenario: Desktop width
- **WHEN** the page is shown at 1440 px width
- **THEN** there is no horizontal scroll and the content column is centered and narrower than the viewport

### Requirement: Page language
The page SHALL show all its own texts (the texts this spec defines, plus placeholder, button, loading indicator, accessible names and document title) in Spanish when the visitor's highest-priority browser language, by the request's `Accept-Language` header, is `es`, `ca`, `gl` or `eu`, or any regional tag of them (`es-*`, `ca-*`, `gl-*`, `eu-*`), and in English otherwise, including when the header is missing. The page MUST declare that language as its document language.

#### Scenario: Spanish browser
- **WHEN** a visitor whose browser language is `es-AR` opens the page
- **THEN** the page texts are in Spanish and the document language is `es`

#### Scenario: Spanish browser from another region
- **WHEN** a visitor whose browser language is `es-ES` opens the page
- **THEN** the page texts are in Spanish

#### Scenario: Other language of Spain
- **WHEN** a visitor whose browser language is `ca-ES`, `gl-ES` or `eu-ES` opens the page
- **THEN** the page texts are in Spanish

#### Scenario: English browser
- **WHEN** a visitor whose browser language is `en-US` opens the page
- **THEN** the page texts are in English and the document language is `en`

#### Scenario: Other browser language
- **WHEN** a visitor whose browser language is `pt-BR` opens the page
- **THEN** the page texts are in English

#### Scenario: Spanish is not the highest priority
- **WHEN** the request's `Accept-Language` header is `en-US,es;q=0.9`
- **THEN** the page texts are in English

#### Scenario: No language preference
- **WHEN** the request has no `Accept-Language` header
- **THEN** the page texts are in English

### Requirement: Content is not translated
The page language SHALL apply only to the page's own texts. The visitor's questions, the answers and the source ids and titles MUST be shown exactly as typed or as returned by the support chat API.

#### Scenario: Spanish source title in an English page
- **WHEN** the page is in English and the API answers with source NIM-020 and a Spanish title
- **THEN** the source is shown as "NIM-020" with the Spanish title as returned

### Requirement: Expiry warning
When 5 minutes or less are left before the conversation expires, the page SHALL show, near the input, the expiry warning in the page language. The time left is taken from the `expires_in_seconds` of the most recent answered question. In Spanish the warning is "Tu conversación vence en menos de 5 minutos por inactividad. Hacé una pregunta para continuarla.", and in English "Your conversation expires in less than 5 minutes due to inactivity. Ask a question to keep it going." A new answered question MUST hide the warning.

#### Scenario: Warning after 10 idle minutes
- **WHEN** an answer with `expires_in_seconds` 900 is shown and 10 minutes pass with no new question
- **THEN** the expiry warning is visible near the input

#### Scenario: No warning before
- **WHEN** an answer with `expires_in_seconds` 900 is shown and 9 minutes pass with no new question
- **THEN** the expiry warning is not visible

#### Scenario: New answer hides the warning
- **WHEN** the expiry warning is visible and the visitor's next question is answered
- **THEN** the expiry warning is hidden

#### Scenario: English expiry warning
- **WHEN** the page is in English and the expiry warning is shown
- **THEN** the English expiry warning is visible

### Requirement: Conversation expires on the page
When the time given by the most recent answered question's `expires_in_seconds` passes with no new answered question, the page SHALL replace the expiry warning with the expired notice in the page language. In Spanish the notice is "La conversación expiró por inactividad. Tu próxima pregunta empieza una conversación nueva.", and in English "The conversation expired due to inactivity. Your next question starts a new conversation." Earlier questions and answers MUST stay visible. The next question MUST be sent without a conversation id.

#### Scenario: Conversation expires after 15 idle minutes
- **WHEN** an answer with `expires_in_seconds` 900 is shown and 15 minutes pass with no new question
- **THEN** the expired notice is visible, the earlier question and answer are still shown, and the next question is sent without `conversation_id`

#### Scenario: English expired notice
- **WHEN** the page is in English and the conversation expires on the page
- **THEN** the English expired notice is visible

### Requirement: Expired notice lasts until the next answer
The expired notice SHALL stay visible until the next question is answered, and MUST be hidden then. A question that fails MUST NOT hide it.

#### Scenario: Expired notice hides after the next answer
- **WHEN** the expired notice is visible and the visitor's next question is answered
- **THEN** the expired notice is hidden

#### Scenario: Expired notice stays after a failed question
- **WHEN** the expired notice is visible and the visitor's next question receives `503`
- **THEN** the expired notice is still visible

### Requirement: Answer that arrives after the page expired the conversation
When a question sent with a `conversation_id` is still waiting for its answer as the conversation expires on the page, and the API then answers it, the page SHALL show the answer and continue the conversation with that answer's `conversation_id`, as for any answered question.

#### Scenario: Pending answer arrives after page expiry
- **WHEN** a question sent with a `conversation_id` is pending as the conversation expires on the page, and the API then answers it with `200`
- **THEN** the answer is shown, the expired notice is hidden, and the next question is sent with the `conversation_id` of that answer
