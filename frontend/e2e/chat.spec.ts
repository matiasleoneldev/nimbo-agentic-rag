import { expect, type Page, type Route, test } from "@playwright/test";

const SUGGESTIONS = [
  "¿Cuánto cuesta un retiro inmediato a mi cuenta bancaria?",
  "¿Cómo activo la verificación en dos pasos?",
  "¿Qué hago si un vendedor no me envió lo que compré?",
  "¿Por qué mi dinero está retenido?",
];
const CONVERSATION = { conversation_id: "conv-1", expires_in_seconds: 900 };
const FEE_ANSWER = {
  answer: "Cuesta 1,5% del monto.\nCon un mínimo por país.",
  sources: [{ id: "NIM-020", title: "Comisiones para Cuentas Personales" }],
  ...CONVERSATION,
};

type Handler = (route: Route) => Promise<void>;
type SentBody = { question: string; conversation_id?: string };

/** Intercepts POST /api/chat; returns the request bodies the page sent. */
async function mockChat(page: Page, handler: Handler): Promise<SentBody[]> {
  const sent: SentBody[] = [];
  await page.route("**/api/chat", async (route) => {
    sent.push(route.request().postDataJSON() as SentBody);
    await handler(route);
  });
  return sent;
}

/** Holds every POST /api/chat until `release` is called, then answers with FEE_ANSWER. */
async function holdChat(page: Page) {
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  const sent = await mockChat(page, async (route) => {
    await held;
    await route.fulfill({ status: 200, json: FEE_ANSWER });
  });
  return { sent, release };
}

const questionsOf = (sent: SentBody[]) => sent.map((body) => body.question);
const dots = (page: Page) => page.getByRole("status").getByTestId("typing-dot");
const animationNames = (page: Page) =>
  dots(page).evaluateAll((elements) => elements.map((e) => getComputedStyle(e).animationName));

const reply =
  (status: number, json: unknown): Handler =>
  (route) =>
    route.fulfill({ status, json });

const input = (page: Page) => page.getByRole("textbox", { name: "Tu pregunta" });
// Scoped: Next.js renders its own role="alert" route announcer.
const errors = (page: Page) =>
  page.getByRole("list", { name: "Conversación" }).getByRole("alert");
const suggestions = (page: Page) =>
  page.getByRole("region", { name: "Preguntas sugeridas" }).getByRole("button");

test.beforeEach(async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("textbox")).toBeEnabled(); // hydrated, in any language
});

test("shows title and subtitle", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Centro de Ayuda Nimbo" })).toBeVisible();
  await expect(
    page.getByText(
      "Hacé tu pregunta sobre tu cuenta, pagos, comisiones o la Tarjeta Nimbo en Argentina, México, Colombia y Chile. Respondemos con la información del Centro de Ayuda.",
    ),
  ).toBeVisible();
});

test("sends question on Enter", async ({ page }) => {
  const sent = await mockChat(page, reply(200, FEE_ANSWER));

  await input(page).fill("¿Cuánto cuesta?");
  await input(page).press("Enter");

  await expect(page.getByTestId("answer")).toBeVisible();
  expect(questionsOf(sent)).toEqual(["¿Cuánto cuesta?"]);
});

test("does not send blank question", async ({ page }) => {
  const sent = await mockChat(page, reply(200, FEE_ANSWER));

  await input(page).fill("   ");
  await input(page).press("Enter");
  await page.getByRole("button", { name: "Enviar" }).click();

  await page.waitForTimeout(300);
  expect(questionsOf(sent)).toEqual([]);
});

test("caps input at 500 characters", async ({ page }) => {
  await input(page).fill("a".repeat(600));

  await expect(input(page)).toHaveValue("a".repeat(500));
});

test("shows suggested questions in order below input", async ({ page }) => {
  await expect(suggestions(page)).toHaveText(SUGGESTIONS);

  const inputBox = await input(page).boundingBox();
  const boxes = await Promise.all((await suggestions(page).all()).map((b) => b.boundingBox()));
  expect(inputBox).not.toBeNull();
  let previousBottom = inputBox!.y + inputBox!.height;
  for (const box of boxes) {
    expect(box).not.toBeNull();
    expect(box!.y).toBeGreaterThanOrEqual(previousBottom); // one per row, below the input
    expect(box!.x).toBeCloseTo(boxes[0]!.x, 0);
    previousBottom = box!.y + box!.height;
  }
});

test("hides suggestions while typing", async ({ page }) => {
  await input(page).fill("h");

  await expect(suggestions(page)).toHaveCount(0);
});

test("shows suggestions again when input is cleared", async ({ page }) => {
  await input(page).fill("hola");
  await input(page).fill("");

  await expect(suggestions(page)).toHaveCount(4);
});

test("clicking a suggestion sends it", async ({ page }) => {
  const sent = await mockChat(page, reply(200, FEE_ANSWER));

  await page.getByRole("button", { name: SUGGESTIONS[3] }).click();

  await expect(page.getByRole("list", { name: "Conversación" })).toContainText(SUGGESTIONS[3]);
  expect(questionsOf(sent)).toEqual([SUGGESTIONS[3]]);
});

test("shows answer with sources", async ({ page }) => {
  await mockChat(page, reply(200, FEE_ANSWER));

  await input(page).fill("¿Cuánto cuesta?");
  await input(page).press("Enter");

  const conversation = page.getByRole("list", { name: "Conversación" });
  await expect(conversation.getByText("¿Cuánto cuesta?")).toBeVisible();
  await expect(page.getByTestId("answer")).toHaveText(FEE_ANSWER.answer);
  const sources = page.getByRole("list", { name: "Fuentes" });
  await expect(sources).toContainText("NIM-020");
  await expect(sources).toContainText("Comisiones para Cuentas Personales");
  await expect(sources.getByRole("link")).toHaveCount(0);
});

test("renders answer markup as text", async ({ page }) => {
  await mockChat(page, reply(200, { answer: "<b>hola</b>", sources: [], ...CONVERSATION }));

  await input(page).fill("markup");
  await input(page).press("Enter");

  await expect(page.getByTestId("answer")).toHaveText("<b>hola</b>");
  await expect(page.locator("[data-testid=answer] b")).toHaveCount(0);
});

test("clears input after sending", async ({ page }) => {
  await mockChat(page, reply(200, FEE_ANSWER));

  await input(page).fill("¿Cuánto cuesta?");
  await input(page).press("Enter");

  await expect(input(page)).toHaveValue("");
  await expect(suggestions(page)).toHaveCount(0);
});

test("hides suggestions once the conversation has started", async ({ page }) => {
  await mockChat(page, reply(200, FEE_ANSWER));

  await input(page).fill("¿Cuánto cuesta?");
  await input(page).press("Enter");

  await expect(page.getByTestId("answer")).toBeVisible();
  await expect(input(page)).toHaveValue("");
  await expect(suggestions(page)).toHaveCount(0);
});

test("hides suggestions after a failed question", async ({ page }) => {
  await mockChat(page, reply(503, { detail: "down" }));

  await input(page).fill("¿Cuánto cuesta?");
  await input(page).press("Enter");

  await expect(errors(page)).toHaveText(
    "No pudimos responder tu pregunta. Intentalo de nuevo más tarde.",
  );
  await expect(suggestions(page)).toHaveCount(0);
});

test("shows suggestions again after reload", async ({ page }) => {
  await mockChat(page, reply(200, FEE_ANSWER));
  await input(page).fill("¿Cuánto cuesta?");
  await input(page).press("Enter");
  await expect(page.getByTestId("answer")).toBeVisible();

  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(input(page)).toBeEnabled();

  await expect(suggestions(page)).toHaveCount(4);
});

test("shows a three-dot indicator while pending", async ({ page }) => {
  const { release } = await holdChat(page);

  await input(page).fill("Primera");
  await input(page).press("Enter");

  await expect(page.getByRole("status")).toHaveText("Buscando en el Centro de Ayuda…");
  await expect(dots(page)).toHaveCount(3);
  expect(await animationNames(page)).not.toContain("none");
  release();
  await expect(page.getByTestId("answer")).toBeVisible();
  await expect(page.getByRole("status")).toHaveCount(0);
});

test("bounces the dots in sequence", async ({ page }) => {
  const { release } = await holdChat(page);

  await input(page).fill("Primera");
  await input(page).press("Enter");

  await expect(dots(page)).toHaveCount(3);
  const delays = await dots(page).evaluateAll((elements) =>
    elements.map((e) => getComputedStyle(e).animationDelay),
  );
  expect(delays).toEqual(["-0.3s", "-0.15s", "0s"]);
  release();
});

test("does not animate the indicator with reduced motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const { release } = await holdChat(page);

  await input(page).fill("Primera");
  await input(page).press("Enter");

  await expect(dots(page)).toHaveCount(3);
  expect(await animationNames(page)).toEqual(["none", "none", "none"]);
  release();
});

test("does not send while an answer is pending", async ({ page }) => {
  const { sent, release } = await holdChat(page);

  await input(page).fill("Primera");
  await input(page).press("Enter");
  await expect(page.getByRole("status")).toBeVisible();
  await input(page).fill("Segunda");
  await input(page).press("Enter");
  await page.getByRole("button", { name: "Enviar" }).click({ force: true });
  release();

  await expect(page.getByTestId("answer")).toBeVisible();
  expect(questionsOf(sent)).toEqual(["Primera"]);
});

test("shows sensitive data notice", async ({ page }) => {
  await expect(
    page.getByText("No compartas contraseñas, códigos de verificación ni datos de tarjetas."),
  ).toBeVisible();
});

test("shows fictional company footer", async ({ page }) => {
  const footer = page.getByRole("contentinfo");
  await footer.scrollIntoViewIfNeeded();

  await expect(footer).toHaveText(
    "Nimbo es una empresa ficticia. Este sitio es una demo con fines de portfolio.",
  );
});

test("shows rate limit message on 429", async ({ page }) => {
  await mockChat(page, reply(429, { detail: "Too many questions." }));

  await input(page).fill("¿Cuánto cuesta?");
  await input(page).press("Enter");

  await expect(errors(page)).toHaveText(
    "Hiciste muchas preguntas seguidas. Esperá un momento y volvé a intentarlo.",
  );
  await expect(input(page)).toBeEnabled();
});

test("shows generic error on failure", async ({ page }) => {
  let calls = 0;
  await mockChat(page, async (route) => {
    calls += 1;
    if (calls === 1) await route.fulfill({ status: 503, json: { detail: "down" } });
    else await route.abort();
  });
  const message = "No pudimos responder tu pregunta. Intentalo de nuevo más tarde.";

  await input(page).fill("Primera");
  await input(page).press("Enter");
  await expect(errors(page)).toHaveText(message);
  await input(page).fill("Segunda");
  await input(page).press("Enter");

  await expect(errors(page)).toHaveText([message, message]);
});

test("has no horizontal scroll at phone width", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "phone", "phone viewport only");

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  for (const locator of [page.getByRole("heading"), input(page), ...(await suggestions(page).all())]) {
    const box = await locator.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(375);
  }
});

test("centers content at desktop width", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "desktop viewport only");

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  const box = (await page.getByRole("main").boundingBox())!;
  expect(box.width).toBeLessThan(1440);
  expect(Math.abs(box.x - (1440 - box.x - box.width))).toBeLessThanOrEqual(2);
});

const WARNING =
  "Tu conversación vence en menos de 5 minutos por inactividad. Hacé una pregunta para continuarla.";
const EXPIRED =
  "La conversación expiró por inactividad. Tu próxima pregunta empieza una conversación nueva.";
const EN_WARNING =
  "Your conversation expires in less than 5 minutes due to inactivity. Ask a question to keep it going.";
const EN_EXPIRED =
  "The conversation expired due to inactivity. Your next question starts a new conversation.";

/** Installs page.clock, which must happen before the page loads, then reloads the page. */
async function withFakeClock(page: Page) {
  await page.clock.install();
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("textbox")).toBeEnabled();
}

async function ask(page: Page, question: string, answers: number) {
  await input(page).fill(question);
  await input(page).press("Enter");
  await expect(page.getByTestId("answer")).toHaveCount(answers);
}

test.describe("conversation", () => {
  test("sends conversation id with follow-up questions", async ({ page }) => {
    const sent = await mockChat(page, reply(200, FEE_ANSWER));

    await ask(page, "Primera", 1);
    await ask(page, "Segunda", 2);

    expect(sent).toEqual([
      { question: "Primera" },
      { question: "Segunda", conversation_id: "conv-1" },
    ]);
  });

  test("starts a new conversation after reload", async ({ page }) => {
    const sent = await mockChat(page, reply(200, FEE_ANSWER));
    await ask(page, "Primera", 1);

    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(input(page)).toBeEnabled();
    await expect(page.getByRole("list", { name: "Conversación" })).toHaveCount(0);
    await ask(page, "Segunda", 1);

    expect(sent[1]).toEqual({ question: "Segunda" });
  });

  test("shows expiry warning after 10 idle minutes", async ({ page }) => {
    await withFakeClock(page);
    await mockChat(page, reply(200, FEE_ANSWER));
    await ask(page, "Primera", 1);

    await page.clock.fastForward("10:00");

    await expect(page.getByText(WARNING)).toBeVisible();
  });

  test("does not show expiry warning before 10 minutes", async ({ page }) => {
    await withFakeClock(page);
    await mockChat(page, reply(200, FEE_ANSWER));
    await ask(page, "Primera", 1);

    await page.clock.fastForward("09:00");

    await expect(page.getByText(WARNING)).toHaveCount(0);
  });

  test("hides expiry warning after a new answer", async ({ page }) => {
    await withFakeClock(page);
    await mockChat(page, reply(200, FEE_ANSWER));
    await ask(page, "Primera", 1);
    await page.clock.fastForward("10:00");
    await expect(page.getByText(WARNING)).toBeVisible();

    await ask(page, "Segunda", 2);

    await expect(page.getByText(WARNING)).toHaveCount(0);
  });

  test("expires conversation after 15 idle minutes", async ({ page }) => {
    await withFakeClock(page);
    const sent = await mockChat(page, reply(200, FEE_ANSWER));
    await ask(page, "Primera", 1);

    await page.clock.fastForward("15:00");

    await expect(page.getByText(EXPIRED)).toBeVisible();
    await expect(page.getByText(WARNING)).toHaveCount(0);
    const conversation = page.getByRole("list", { name: "Conversación" });
    await expect(conversation.getByText("Primera")).toBeVisible();
    await expect(page.getByTestId("answer")).toHaveText(FEE_ANSWER.answer);
    await ask(page, "Segunda", 2);
    expect(sent[1]).toEqual({ question: "Segunda" });
  });

  test("hides expired notice after the next answer", async ({ page }) => {
    await withFakeClock(page);
    await mockChat(page, reply(200, FEE_ANSWER));
    await ask(page, "Primera", 1);
    await page.clock.fastForward("15:00");
    await expect(page.getByText(EXPIRED)).toBeVisible();

    await ask(page, "Segunda", 2);

    await expect(page.getByText(EXPIRED)).toHaveCount(0);
  });

  test("keeps expired notice after a failed question", async ({ page }) => {
    await withFakeClock(page);
    let calls = 0;
    await mockChat(page, async (route) => {
      calls += 1;
      await route.fulfill(
        calls === 1 ? { status: 200, json: FEE_ANSWER } : { status: 503, json: { detail: "down" } },
      );
    });
    await ask(page, "Primera", 1);
    await page.clock.fastForward("15:00");
    await expect(page.getByText(EXPIRED)).toBeVisible();

    await input(page).fill("Segunda");
    await input(page).press("Enter");
    await expect(errors(page)).toHaveCount(1);

    await expect(page.getByText(EXPIRED)).toBeVisible();
  });

  test("keeps the conversation when a pending answer arrives after page expiry", async ({
    page,
  }) => {
    await withFakeClock(page);
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => (release = resolve));
    let calls = 0;
    const sent = await mockChat(page, async (route) => {
      calls += 1;
      if (calls === 2) await held;
      await route.fulfill({ status: 200, json: FEE_ANSWER });
    });
    await ask(page, "Primera", 1);
    await input(page).fill("Segunda");
    await input(page).press("Enter");
    await expect(page.getByText("Buscando en el Centro de Ayuda…")).toBeVisible();

    await page.clock.fastForward("15:00");
    await expect(page.getByText(EXPIRED)).toBeVisible();
    release();
    await expect(page.getByTestId("answer")).toHaveCount(2);

    await expect(page.getByText(EXPIRED)).toHaveCount(0);
    await ask(page, "Tercera", 3);
    expect(sent[1]).toEqual({ question: "Segunda", conversation_id: "conv-1" });
    expect(sent[2]).toEqual({ question: "Tercera", conversation_id: "conv-1" });
  });

  test("shows expired message on 404 and starts a new conversation", async ({ page }) => {
    let calls = 0;
    const sent = await mockChat(page, async (route) => {
      calls += 1;
      await route.fulfill(
        calls === 2
          ? { status: 404, json: { detail: "Conversation not found." } }
          : { status: 200, json: FEE_ANSWER },
      );
    });
    await ask(page, "Primera", 1);

    await input(page).fill("Segunda");
    await input(page).press("Enter");

    await expect(errors(page)).toHaveText("La conversación expiró. Volvé a hacer tu pregunta.");
    await ask(page, "Tercera", 2);
    expect(sent[1]).toEqual({ question: "Segunda", conversation_id: "conv-1" });
    expect(sent[2]).toEqual({ question: "Tercera" });
  });
});

const EN_SUGGESTIONS = [
  "How much does an instant withdrawal to my bank account cost?",
  "How do I turn on two-step verification?",
  "What do I do if a seller didn't send what I bought?",
  "Why is my money on hold?",
];
const EN_TITLE = "Nimbo Help Center";
const EN_SUBTITLE =
  "Ask about your account, payments, fees or the Nimbo Card in Argentina, Mexico, Colombia and Chile. We answer with information from the Help Center.";

const enInput = (page: Page) => page.getByRole("textbox", { name: "Your question" });
const enErrors = (page: Page) =>
  page.getByRole("list", { name: "Conversation" }).getByRole("alert");

test.describe("page language", () => {
  test.describe("Spanish", () => {
    test("shows Spanish for es-AR browser", async ({ page }) => {
      await expect(page.getByRole("heading", { name: "Centro de Ayuda Nimbo" })).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("lang", "es");
    });

    for (const locale of ["es-ES", "ca-ES", "gl-ES", "eu-ES"]) {
      test.describe(locale, () => {
        test.use({ locale });
        test(`shows Spanish for ${locale} browser`, async ({ page }) => {
          await expect(page.getByRole("heading", { name: "Centro de Ayuda Nimbo" })).toBeVisible();
        });
      });
    }
  });

  test.describe("English", () => {
    test.describe("en-US", () => {
      test.use({ locale: "en-US" });
      test("shows English for en-US browser", async ({ page }) => {
        await expect(page.getByRole("heading", { name: EN_TITLE })).toBeVisible();
        await expect(page.locator("html")).toHaveAttribute("lang", "en");
      });
    });

    test.describe("pt-BR", () => {
      test.use({ locale: "pt-BR" });
      test("shows English for pt-BR browser", async ({ page }) => {
        await expect(page.getByRole("heading", { name: EN_TITLE })).toBeVisible();
      });
    });

    test.describe("Spanish not first", () => {
      test.use({ locale: "en-US", extraHTTPHeaders: { "Accept-Language": "en-US,es;q=0.9" } });
      test("shows English when Spanish is not first", async ({ page }) => {
        await expect(page.getByRole("heading", { name: EN_TITLE })).toBeVisible();
      });
    });

    test("shows English without Accept-Language", async ({ request }) => {
      const response = await request.get("/", );
      const html = await response.text();
      expect(html).toContain('lang="en"');
      expect(html).toContain(EN_TITLE);
    });
  });
});

test.describe("English page", () => {
  test.use({ locale: "en-US" });

  test("keeps source titles as returned in English page", async ({ page }) => {
    await mockChat(page, reply(200, FEE_ANSWER));

    await enInput(page).fill("How much?");
    await enInput(page).press("Enter");

    const sources = page.getByRole("list", { name: "Sources" });
    await expect(sources).toContainText("NIM-020");
    await expect(sources).toContainText("Comisiones para Cuentas Personales");
  });

  test("shows English loading indicator", async ({ page }) => {
    const { release } = await holdChat(page);

    await enInput(page).fill("How much?");
    await enInput(page).press("Enter");

    await expect(page.getByRole("status")).toHaveText("Searching the Help Center…");
    release();
  });

  test("shows English title and subtitle", async ({ page }) => {
    await expect(page.getByRole("heading", { name: EN_TITLE })).toBeVisible();
    await expect(page.getByText(EN_SUBTITLE)).toBeVisible();
  });

  test("shows English suggested questions in order", async ({ page }) => {
    await expect(
      page.getByRole("region", { name: "Suggested questions" }).getByRole("button"),
    ).toHaveText(EN_SUGGESTIONS);
  });

  test("shows English sensitive data notice", async ({ page }) => {
    await expect(
      page.getByText("Don't share passwords, verification codes or card details."),
    ).toBeVisible();
  });

  test("shows English fictional company footer", async ({ page }) => {
    const footer = page.getByRole("contentinfo");
    await footer.scrollIntoViewIfNeeded();

    await expect(footer).toHaveText("Nimbo is a fictional company. This site is a portfolio demo.");
  });

  test("shows English error messages", async ({ page }) => {
    let calls = 0;
    await mockChat(page, async (route) => {
      calls += 1;
      await route.fulfill(
        calls === 1
          ? { status: 429, json: { detail: "Too many questions." } }
          : calls === 2
            ? { status: 503, json: { detail: "down" } }
            : { status: 404, json: { detail: "Conversation not found." } },
      );
    });

    await enInput(page).fill("First");
    await enInput(page).press("Enter");
    await expect(enErrors(page)).toHaveText(
      "You asked too many questions in a row. Wait a moment and try again.",
    );
    await enInput(page).fill("Second");
    await enInput(page).press("Enter");

    await expect(enErrors(page)).toHaveText([
      "You asked too many questions in a row. Wait a moment and try again.",
      "We couldn't answer your question. Try again later.",
    ]);
    await enInput(page).fill("Third");
    await enInput(page).press("Enter");

    await expect(enErrors(page)).toHaveText([
      "You asked too many questions in a row. Wait a moment and try again.",
      "We couldn't answer your question. Try again later.",
      "The conversation expired. Ask your question again.",
    ]);
  });

  test("shows English expiry warning", async ({ page }) => {
    await withFakeClock(page);
    await mockChat(page, reply(200, FEE_ANSWER));
    await enInput(page).fill("How much?");
    await enInput(page).press("Enter");
    await expect(page.getByTestId("answer")).toBeVisible();

    await page.clock.fastForward("10:00");

    await expect(page.getByText(EN_WARNING)).toBeVisible();
  });

  test("shows English expired notice", async ({ page }) => {
    await withFakeClock(page);
    await mockChat(page, reply(200, FEE_ANSWER));
    await enInput(page).fill("How much?");
    await enInput(page).press("Enter");
    await expect(page.getByTestId("answer")).toBeVisible();

    await page.clock.fastForward("15:00");

    await expect(page.getByText(EN_EXPIRED)).toBeVisible();
  });
});
