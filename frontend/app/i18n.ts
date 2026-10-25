import { headers } from "next/headers";

export type Language = "es" | "en";

export type Dictionary = {
  title: string;
  subtitle: string;
  description: string;
  placeholder: string;
  send: string;
  loading: string;
  sensitiveNotice: string;
  footer: string;
  rateLimitError: string;
  genericError: string;
  expiredError: string;
  expiryWarning: string;
  expiredNotice: string;
  inputLabel: string;
  conversationLabel: string;
  sourcesLabel: string;
  suggestionsLabel: string;
  suggestions: readonly string[];
};

export const dictionaries: Record<Language, Dictionary> = {
  es: {
    title: "Centro de Ayuda Nimbo",
    subtitle:
      "Hacé tu pregunta sobre tu cuenta, pagos, comisiones o la Tarjeta Nimbo en Argentina, México, Colombia y Chile. Respondemos con la información del Centro de Ayuda.",
    description: "Respuestas sobre tu cuenta, pagos y comisiones de Nimbo (empresa ficticia, demo).",
    placeholder: "Escribí tu pregunta…",
    send: "Enviar",
    loading: "Buscando en el Centro de Ayuda…",
    sensitiveNotice: "No compartas contraseñas, códigos de verificación ni datos de tarjetas.",
    footer: "Nimbo es una empresa ficticia. Este sitio es una demo con fines de portfolio.",
    rateLimitError: "Hiciste muchas preguntas seguidas. Esperá un momento y volvé a intentarlo.",
    genericError: "No pudimos responder tu pregunta. Intentalo de nuevo más tarde.",
    expiredError: "La conversación expiró. Volvé a hacer tu pregunta.",
    expiryWarning:
      "Tu conversación vence en menos de 5 minutos por inactividad. Hacé una pregunta para continuarla.",
    expiredNotice:
      "La conversación expiró por inactividad. Tu próxima pregunta empieza una conversación nueva.",
    inputLabel: "Tu pregunta",
    conversationLabel: "Conversación",
    sourcesLabel: "Fuentes",
    suggestionsLabel: "Preguntas sugeridas",
    suggestions: [
      "¿Cuánto cuesta un retiro inmediato a mi cuenta bancaria?",
      "¿Cómo activo la verificación en dos pasos?",
      "¿Qué hago si un vendedor no me envió lo que compré?",
      "¿Por qué mi dinero está retenido?",
    ],
  },
  en: {
    title: "Nimbo Help Center",
    subtitle:
      "Ask about your account, payments, fees or the Nimbo Card in Argentina, Mexico, Colombia and Chile. We answer with information from the Help Center.",
    description:
      "Answers about your Nimbo account, payments and fees (fictional company, demo).",
    placeholder: "Type your question…",
    send: "Send",
    loading: "Searching the Help Center…",
    sensitiveNotice: "Don't share passwords, verification codes or card details.",
    footer: "Nimbo is a fictional company. This site is a portfolio demo.",
    rateLimitError: "You asked too many questions in a row. Wait a moment and try again.",
    genericError: "We couldn't answer your question. Try again later.",
    expiredError: "The conversation expired. Ask your question again.",
    expiryWarning:
      "Your conversation expires in less than 5 minutes due to inactivity. Ask a question to keep it going.",
    expiredNotice:
      "The conversation expired due to inactivity. Your next question starts a new conversation.",
    inputLabel: "Your question",
    conversationLabel: "Conversation",
    sourcesLabel: "Sources",
    suggestionsLabel: "Suggested questions",
    suggestions: [
      "How much does an instant withdrawal to my bank account cost?",
      "How do I turn on two-step verification?",
      "What do I do if a seller didn't send what I bought?",
      "Why is my money on hold?",
    ],
  },
};

const SPANISH_SUBTAGS = new Set(["es", "ca", "gl", "eu"]);

/** Spanish when the highest-priority `Accept-Language` tag is es/ca/gl/eu; English otherwise. */
export async function getLanguage(): Promise<Language> {
  const header = (await headers()).get("accept-language") ?? "";
  let best = { tag: "", q: 0 };
  for (const part of header.split(",")) {
    const [tag = "", ...params] = part.trim().split(";");
    const qParam = params.map((p) => p.trim()).find((p) => p.startsWith("q="));
    const q = qParam === undefined ? 1 : Number(qParam.slice(2));
    if (tag && q > best.q) best = { tag, q }; // strict >: earliest wins a tie; also drops q=0 and NaN
  }
  const primary = best.tag.split("-")[0]?.toLowerCase() ?? "";
  return SPANISH_SUBTAGS.has(primary) ? "es" : "en";
}
