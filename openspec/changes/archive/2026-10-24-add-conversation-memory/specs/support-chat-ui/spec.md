# Spec Delta

## ADDED Requirements

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

## MODIFIED Requirements

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
- **THEN** the input is empty and the suggested questions are visible

#### Scenario: Follow-up continues the conversation
- **WHEN** the first question is answered with a `conversation_id` and the visitor sends a second question
- **THEN** the first question is sent without `conversation_id` and the second question is sent with the `conversation_id` of the first answer

#### Scenario: Reload starts a new conversation
- **WHEN** the visitor has an answered question, reloads the page and sends a question
- **THEN** the conversation shown is empty before sending, and the question is sent without `conversation_id`

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
