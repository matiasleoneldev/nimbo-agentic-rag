# Spec Delta

## Purpose

Defines the public web page visitors use to ask the Nimbo support chat questions: layout, suggested questions, input rules, how answers and sources are shown, error states and responsive behavior.

## ADDED Requirements

### Requirement: Page header
The page SHALL be publicly reachable without authentication and show the title "Centro de Ayuda Nimbo" and the subtitle "Hacé tu pregunta sobre tu cuenta, pagos, comisiones o la Tarjeta Nimbo. Respondemos con la información del Centro de Ayuda."

#### Scenario: Header is visible
- **WHEN** a visitor opens the page
- **THEN** the title and subtitle are visible, with no login prompt

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
While the input is empty, the page SHALL show, below the input and stacked in a single column at every screen width, exactly these suggested questions in this order: "¿Cuánto cuesta un retiro inmediato a mi cuenta bancaria?", "¿Cómo activo la verificación en dos pasos?", "¿Qué hago si un vendedor no me envió lo que compré?", "¿Por qué mi dinero está retenido?". While the input contains any character, the suggested questions MUST be hidden.

#### Scenario: Suggestions shown on empty input
- **WHEN** the page loads
- **THEN** the four suggested questions are visible below the input, in the specified order, one per row

#### Scenario: Suggestions hidden while typing
- **WHEN** the visitor types any character in the input
- **THEN** the suggested questions are hidden

#### Scenario: Suggestions return when input is cleared
- **WHEN** the visitor deletes all characters from the input
- **THEN** the suggested questions are visible again

### Requirement: Clicking a suggested question asks it
Clicking a suggested question SHALL put its text in the input and send it as the question, exactly as if the visitor had typed it and pressed send.

#### Scenario: Click sends the suggestion
- **WHEN** the visitor clicks "¿Por qué mi dinero está retenido?"
- **THEN** a request with that question is sent and the question appears in the conversation

### Requirement: Conversation display
Each sent question and its answer SHALL be shown on the page in the order they were asked, as plain text with line breaks preserved. Under each answer that has sources, the page MUST show each source's id and title as plain text, not as links. After a question is sent, the input MUST be cleared. Reloading the page MUST start with an empty conversation.

#### Scenario: Answer with sources
- **WHEN** the API answers with sources NIM-020
- **THEN** the answer text is shown under its question, followed by "NIM-020" and its title, with no link

#### Scenario: Answer markup is not rendered
- **WHEN** an answer contains the text `<b>hola</b>`
- **THEN** the page shows the literal characters `<b>hola</b>`, not bold text

#### Scenario: Input clears after sending
- **WHEN** a question is sent
- **THEN** the input is empty and the suggested questions are visible

### Requirement: Sensitive data notice
The page SHALL show, next to the input, the notice "No compartas contraseñas, códigos de verificación ni datos de tarjetas." at all times.

#### Scenario: Notice is visible
- **WHEN** a visitor opens the page
- **THEN** the sensitive data notice is visible near the input

### Requirement: Fictional company notice
The page SHALL show, in its footer, the text "Nimbo es una empresa ficticia. Este sitio es una demo con fines de portfolio."

#### Scenario: Footer notice is visible
- **WHEN** a visitor opens the page and scrolls to the bottom
- **THEN** the fictional company notice is visible

### Requirement: Pending state
While a question is waiting for its answer, the page SHALL show a loading indicator for it and MUST NOT send another question (send button and suggested questions disabled).

#### Scenario: No double send
- **WHEN** an answer is pending and the visitor clicks a suggested question
- **THEN** no new request is sent

### Requirement: Error messages
When the API rejects a question or fails, the page SHALL show an error message in place of the answer and keep the page usable. A `429` response MUST show "Hiciste muchas preguntas seguidas. Esperá un momento y volvé a intentarlo."; any other failure (including network errors) MUST show "No pudimos responder tu pregunta. Intentalo de nuevo más tarde."

#### Scenario: Rate limited
- **WHEN** the API responds `429`
- **THEN** the rate-limit message is shown and the visitor can type a new question

#### Scenario: Server error
- **WHEN** the API responds `503` or the request fails
- **THEN** the generic error message is shown

### Requirement: Responsive layout
The page SHALL be usable from 320 px to 1920 px viewport width with no horizontal scrolling. On narrow viewports the input spans the available width; on wide viewports the content is centered with a bounded width.

#### Scenario: Phone width
- **WHEN** the page is shown at 375 px width
- **THEN** there is no horizontal scroll and the title, input and suggested questions are fully visible within the viewport width

#### Scenario: Desktop width
- **WHEN** the page is shown at 1440 px width
- **THEN** there is no horizontal scroll and the content column is centered and narrower than the viewport
