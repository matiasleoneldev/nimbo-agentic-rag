"use client";

import { type FormEvent, useState, useSyncExternalStore } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MAX_QUESTION_LENGTH = 500;

const SUGGESTED_QUESTIONS = [
  "¿Cuánto cuesta un retiro inmediato a mi cuenta bancaria?",
  "¿Cómo activo la verificación en dos pasos?",
  "¿Qué hago si un vendedor no me envió lo que compré?",
  "¿Por qué mi dinero está retenido?",
] as const;

const RATE_LIMIT_MESSAGE = "Hiciste muchas preguntas seguidas. Esperá un momento y volvé a intentarlo.";
const GENERIC_ERROR_MESSAGE = "No pudimos responder tu pregunta. Intentalo de nuevo más tarde.";

type Source = { id: string; title: string };
type ChatResponse = { answer: string; sources: Source[] };

type Entry =
  | { question: string; status: "pending" }
  | { question: string; status: "answered"; answer: string; sources: Source[] }
  | { question: string; status: "error"; message: string };

function isChatResponse(value: unknown): value is ChatResponse {
  if (typeof value !== "object" || value === null) return false;
  const { answer, sources } = value as Record<string, unknown>;
  return (
    typeof answer === "string" &&
    Array.isArray(sources) &&
    sources.every(
      (s: unknown) =>
        typeof s === "object" &&
        s !== null &&
        typeof (s as Record<string, unknown>).id === "string" &&
        typeof (s as Record<string, unknown>).title === "string",
    )
  );
}

async function askQuestion(question: string): Promise<Entry> {
  try {
    const response = await fetch(`${API_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (response.status === 429) return { question, status: "error", message: RATE_LIMIT_MESSAGE };
    const body: unknown = response.ok ? await response.json() : null;
    if (!isChatResponse(body)) return { question, status: "error", message: GENERIC_ERROR_MESSAGE };
    return { question, status: "answered", answer: body.answer, sources: body.sources };
  } catch {
    return { question, status: "error", message: GENERIC_ERROR_MESSAGE };
  }
}

const subscribeNever = () => () => {};

export default function ChatPage() {
  // false in the server HTML, true once React has hydrated: keystrokes typed before
  // hydration would be lost, so the input stays disabled until then.
  const hydrated = useSyncExternalStore(subscribeNever, () => true, () => false);
  const [input, setInput] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const pending = entries.some((entry) => entry.status === "pending");

  async function send(text: string) {
    const question = text.trim();
    if (!question || pending) return;
    setInput("");
    const index = entries.length;
    setEntries((previous) => [...previous, { question, status: "pending" }]);
    const result = await askQuestion(question);
    setEntries((previous) => previous.map((entry, i) => (i === index ? result : entry)));
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void send(input);
  }

  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-4 py-10 sm:py-16">
        <header className="space-y-2">
          <p className="text-sm font-semibold tracking-wide text-sky-700">nimbo</p>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Centro de Ayuda Nimbo</h1>
          <p className="text-base text-slate-600">
            Hacé tu pregunta sobre tu cuenta, pagos, comisiones o la Tarjeta Nimbo. Respondemos con
            la información del Centro de Ayuda.
          </p>
        </header>

        {entries.length > 0 && (
          <ol className="space-y-4" aria-label="Conversación">
            {entries.map((entry, i) => (
              <li key={i} className="space-y-2">
                <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-sky-700 px-4 py-2 break-words text-white">
                  {entry.question}
                </p>
                <div className="max-w-[95%] rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-4 py-3 shadow-sm">
                  {entry.status === "pending" && (
                    <p role="status" className="animate-pulse text-slate-500">
                      Buscando en el Centro de Ayuda…
                    </p>
                  )}
                  {entry.status === "error" && (
                    <p role="alert" className="text-red-700">
                      {entry.message}
                    </p>
                  )}
                  {entry.status === "answered" && (
                    <>
                      <p data-testid="answer" className="whitespace-pre-line break-words">
                        {entry.answer}
                      </p>
                      {entry.sources.length > 0 && (
                        <ul className="mt-3 space-y-1 border-t border-slate-100 pt-2 text-sm text-slate-500" aria-label="Fuentes">
                          {entry.sources.map((source) => (
                            <li key={source.id}>
                              <span className="font-mono font-medium text-slate-700">{source.id}</span> ·{" "}
                              {source.title}
                            </li>
                          ))}
                        </ul>
                      )}
                    </>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}

        <form onSubmit={onSubmit} className="space-y-2">
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              maxLength={MAX_QUESTION_LENGTH}
              disabled={!hydrated}
              placeholder="Escribí tu pregunta…"
              aria-label="Tu pregunta"
              autoComplete="off"
              className="min-w-0 flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 shadow-sm outline-none focus:border-sky-600 focus:ring-2 focus:ring-sky-200"
            />
            <button
              type="submit"
              disabled={pending}
              className="shrink-0 rounded-xl bg-sky-700 px-5 py-3 font-medium text-white hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Enviar
            </button>
          </div>
          <p className="text-xs text-slate-500">
            No compartas contraseñas, códigos de verificación ni datos de tarjetas.
          </p>
        </form>

        {input === "" && (
          <section aria-label="Preguntas sugeridas" className="flex flex-col gap-2">
            {SUGGESTED_QUESTIONS.map((question) => (
              <button
                key={question}
                type="button"
                disabled={pending}
                onClick={() => {
                  setInput(question);
                  void send(question);
                }}
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-slate-700 shadow-sm hover:border-sky-300 hover:bg-sky-50 hover:text-sky-900 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {question}
              </button>
            ))}
          </section>
        )}
      </main>

      <footer className="border-t border-slate-200 bg-white px-4 py-4 text-center text-xs text-slate-600">
        Nimbo es una empresa ficticia. Este sitio es una demo con fines de portfolio.
      </footer>
    </div>
  );
}
