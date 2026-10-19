# Spec Delta

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Page header
The page SHALL be publicly reachable without authentication and show a title and subtitle in the page language. In Spanish, the title is "Centro de Ayuda Nimbo" and the subtitle "Hacé tu pregunta sobre tu cuenta, pagos, comisiones o la Tarjeta Nimbo en Argentina, México, Colombia y Chile. Respondemos con la información del Centro de Ayuda." In English, the title is "Nimbo Help Center" and the subtitle "Ask about your account, payments, fees or the Nimbo Card in Argentina, Mexico, Colombia and Chile. We answer with information from the Help Center."

#### Scenario: Header is visible
- **WHEN** a visitor opens the page
- **THEN** the title and subtitle are visible, with no login prompt

#### Scenario: English header
- **WHEN** a visitor opens the page in English
- **THEN** the English title and subtitle are visible

### Requirement: Suggested questions
While the input is empty, the page SHALL show, below the input and stacked in a single column at every screen width, exactly four suggested questions in the page language, in this order. In Spanish: "¿Cuánto cuesta un retiro inmediato a mi cuenta bancaria?", "¿Cómo activo la verificación en dos pasos?", "¿Qué hago si un vendedor no me envió lo que compré?", "¿Por qué mi dinero está retenido?". In English: "How much does an instant withdrawal to my bank account cost?", "How do I turn on two-step verification?", "What do I do if a seller didn't send what I bought?", "Why is my money on hold?". While the input contains any character, the suggested questions MUST be hidden.

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
- **WHEN** the visitor deletes all characters from the input
- **THEN** the suggested questions are visible again

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

### Requirement: Error messages
When the API rejects a question or fails, the page SHALL show an error message in the page language in place of the answer and keep the page usable. A `429` response MUST show "Hiciste muchas preguntas seguidas. Esperá un momento y volvé a intentarlo." in Spanish and "You asked too many questions in a row. Wait a moment and try again." in English; any other failure (including network errors) MUST show "No pudimos responder tu pregunta. Intentalo de nuevo más tarde." in Spanish and "We couldn't answer your question. Try again later." in English.

#### Scenario: Rate limited
- **WHEN** the API responds `429`
- **THEN** the rate-limit message is shown and the visitor can type a new question

#### Scenario: Server error
- **WHEN** the API responds `503` or the request fails
- **THEN** the generic error message is shown

#### Scenario: English error messages
- **WHEN** the page is in English and the API responds `429`, then `503`
- **THEN** the English rate-limit message is shown, then the English generic error message
