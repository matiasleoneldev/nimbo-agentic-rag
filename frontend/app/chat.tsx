"use client";

import { type FormEvent, useEffect, useState, useSyncExternalStore } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MAX_QUESTION_LENGTH = 500;
// The expiry warning shows this long before the conversation expires.
const WARNING_MS = 5 * 60 * 1000;

import type { Dictionary } from "./i18n";

type Source = { id: string; title: string };
type ChatResponse = {
  answer: string;
  sources: Source[];
  conversation_id: string;
  expires_in_seconds: number;
};

type Entry =
  | { question: string; status: "pending" }
  | { question: string; status: "streaming"; answer: string }
  | { question: string; status: "answered"; answer: string; sources: Source[] }
  | { question: string; status: "error"; message: string };

type Outcome =
  | { entry: Entry; kind: "answered"; conversationId: string; expiresInSeconds: number }
  | { entry: Entry; kind: "expired" | "failed" };

type Expiry = { phase: "active" | "warning" | "expired"; at: number };

function isChatResponse(value: unknown): value is ChatResponse {
  if (typeof value !== "object" || value === null) return false;
  const { answer, sources, conversation_id, expires_in_seconds } = value as Record<string, unknown>;
  return (
    typeof answer === "string" &&
    typeof conversation_id === "string" &&
    typeof expires_in_seconds === "number" &&
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

/** One server-sent event of POST /api/chat/stream: `event: <name>` and `data: <json>` lines. */
function parseEvent(block: string): { event: string; data: unknown } {
  let event = "";
  let data = "null";
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice("event: ".length);
    else if (line.startsWith("data: ")) data = line.slice("data: ".length);
  }
  return { event, data: JSON.parse(data) };
}

async function askQuestion(
  question: string,
  conversationId: string | null,
  t: Dictionary,
  onText: (answer: string) => void,
): Promise<Outcome> {
  const failed = (message: string): Outcome => ({
    entry: { question, status: "error", message },
    kind: "failed",
  });
  try {
    const response = await fetch(`${API_URL}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        conversationId === null ? { question } : { question, conversation_id: conversationId },
      ),
    });
    if (response.status === 429) return failed(t.rateLimitError);
    if (response.status === 404) return { ...failed(t.expiredError), kind: "expired" };
    if (!response.ok || response.body === null) return failed(t.genericError);
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    let answer = "";
    for (;;) {
      const { done, value } = await reader.read();
      // Ended without a done event: the question was not answered.
      if (done) return failed(t.genericError);
      buffer += value;
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        const { event, data } = parseEvent(block);
        if (event === "delta") {
          const { text } = data as Record<string, unknown>;
          if (typeof text !== "string") return failed(t.genericError);
          answer += text;
          onText(answer);
        } else if (event === "done") {
          if (!isChatResponse(data)) return failed(t.genericError);
          return {
            entry: { question, status: "answered", answer: data.answer, sources: data.sources },
            kind: "answered",
            conversationId: data.conversation_id,
            expiresInSeconds: data.expires_in_seconds,
          };
        } else if (event === "error") {
          return failed(t.genericError);
        }
      }
    }
  } catch {
    return failed(t.genericError);
  }
}

const subscribeNever = () => () => {};

export function Chat({ t }: { t: Dictionary }) {
  // false in the server HTML, true once React has hydrated: keystrokes typed before
  // hydration would be lost, so the input stays disabled until then.
  const hydrated = useSyncExternalStore(subscribeNever, () => true, () => false);
  const [input, setInput] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [expiry, setExpiry] = useState<Expiry | null>(null);
  const pending = entries.some((entry) => entry.status === "pending" || entry.status === "streaming");

  // Only a new answer (a new `at`) reschedules; a failed question leaves the timers alone.
  const expiresAt = expiry?.at;
  useEffect(() => {
    if (expiresAt === undefined) return;
    const enter = (phase: Expiry["phase"]) =>
      setExpiry((current) => (current?.at === expiresAt ? { phase, at: expiresAt } : current));
    const warning = setTimeout(() => enter("warning"), expiresAt - WARNING_MS - Date.now());
    const expired = setTimeout(() => {
      enter("expired");
      setConversationId(null);
    }, expiresAt - Date.now());
    return () => {
      clearTimeout(warning);
      clearTimeout(expired);
    };
  }, [expiresAt]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || pending) return;
    setInput("");
    const index = entries.length;
    setEntries((previous) => [...previous, { question, status: "pending" }]);
    const update = (next: Entry) =>
      setEntries((previous) => previous.map((entry, i) => (i === index ? next : entry)));
    const outcome = await askQuestion(question, conversationId, t, (answer) =>
      update({ question, status: "streaming", answer }),
    );
    update(outcome.entry);
    if (outcome.kind === "answered") {
      // Also when the page expired the conversation meanwhile: the API answered it in time.
      setConversationId(outcome.conversationId);
      setExpiry({ phase: "active", at: Date.now() + outcome.expiresInSeconds * 1000 });
    } else if (outcome.kind === "expired") {
      setConversationId(null);
      setExpiry(null);
    }
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
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{t.title}</h1>
          <p className="text-base text-slate-600">{t.subtitle}</p>
        </header>

        {entries.length > 0 && (
          <ol className="space-y-4" aria-label={t.conversationLabel}>
            {entries.map((entry, i) => (
              <li key={i} className="space-y-2">
                <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-sky-700 px-4 py-2 break-words text-white">
                  {entry.question}
                </p>
                <div
                  className={`max-w-[95%] rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-4 py-3 shadow-sm ${entry.status === "pending" ? "w-fit" : ""}`}
                >
                  {entry.status === "pending" && (
                    <p role="status" className="flex h-6 items-center gap-1">
                      <span className="sr-only">{t.loading}</span>
                      {/* Inline: Tailwind's `animate-bounce` shorthand would reset a delay class to 0s. */}
                      {["-0.3s", "-0.15s", "0s"].map((delay) => (
                        <span
                          key={delay}
                          aria-hidden="true"
                          data-testid="typing-dot"
                          style={{ animationDelay: delay }}
                          className="h-2 w-2 rounded-full bg-slate-400 motion-safe:animate-bounce"
                        />
                      ))}
                    </p>
                  )}
                  {entry.status === "error" && (
                    <p role="alert" className="text-red-700">
                      {entry.message}
                    </p>
                  )}
                  {(entry.status === "streaming" || entry.status === "answered") && (
                    <>
                      <p
                        data-testid={entry.status === "answered" ? "answer" : "partial-answer"}
                        aria-busy={entry.status === "streaming"}
                        className="whitespace-pre-line break-words"
                      >
                        {entry.answer}
                      </p>
                      {entry.status === "answered" && entry.sources.length > 0 && (
                        <ul className="mt-3 space-y-1 border-t border-slate-100 pt-2 text-sm text-slate-500" aria-label={t.sourcesLabel}>
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
              placeholder={t.placeholder}
              aria-label={t.inputLabel}
              autoComplete="off"
              className="min-w-0 flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 shadow-sm outline-none focus:border-sky-600 focus:ring-2 focus:ring-sky-200"
            />
            <button
              type="submit"
              disabled={pending}
              className="shrink-0 rounded-xl bg-sky-700 px-5 py-3 font-medium text-white hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t.send}
            </button>
          </div>
          <p className="text-xs text-slate-500">{t.sensitiveNotice}</p>
          {expiry !== null && expiry.phase !== "active" && (
            <p role="status" className="text-xs text-amber-700">
              {expiry.phase === "warning" ? t.expiryWarning : t.expiredNotice}
            </p>
          )}
        </form>

        {entries.length === 0 && input === "" && (
          <section aria-label={t.suggestionsLabel} className="flex flex-col gap-2">
            {t.suggestions.map((question) => (
              <button
                key={question}
                type="button"
                onClick={() => {
                  setInput(question);
                  void send(question);
                }}
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-slate-700 shadow-sm hover:border-sky-300 hover:bg-sky-50 hover:text-sky-900"
              >
                {question}
              </button>
            ))}
          </section>
        )}
      </main>

      <footer className="border-t border-slate-200 bg-white px-4 py-4 text-center text-xs text-slate-600">
        {t.footer}
      </footer>
    </div>
  );
}
