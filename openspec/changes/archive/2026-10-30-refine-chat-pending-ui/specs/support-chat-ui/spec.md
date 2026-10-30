# Spec Delta

## MODIFIED Requirements

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
