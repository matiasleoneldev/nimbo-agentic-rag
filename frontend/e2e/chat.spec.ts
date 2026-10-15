import { expect, type Page, type Route, test } from "@playwright/test";

const SUGGESTIONS = [
  "¿Cuánto cuesta un retiro inmediato a mi cuenta bancaria?",
  "¿Cómo activo la verificación en dos pasos?",
  "¿Qué hago si un vendedor no me envió lo que compré?",
  "¿Por qué mi dinero está retenido?",
];
const FEE_ANSWER = {
  answer: "Cuesta 1,5% del monto.\nCon un mínimo por país.",
  sources: [{ id: "NIM-020", title: "Comisiones para Cuentas Personales" }],
};

type Handler = (route: Route) => Promise<void>;

/** Intercepts POST /api/chat; returns the questions the page sent. */
async function mockChat(page: Page, handler: Handler): Promise<string[]> {
  const questions: string[] = [];
  await page.route("**/api/chat", async (route) => {
    const body: unknown = route.request().postDataJSON();
    if (typeof body === "object" && body !== null && "question" in body) {
      questions.push(String(body.question));
    }
    await handler(route);
  });
  return questions;
}

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
  await expect(input(page)).toBeEnabled(); // hydrated
});

test("shows title and subtitle", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Centro de Ayuda Nimbo" })).toBeVisible();
  await expect(
    page.getByText(
      "Hacé tu pregunta sobre tu cuenta, pagos, comisiones o la Tarjeta Nimbo. Respondemos con la información del Centro de Ayuda.",
    ),
  ).toBeVisible();
});

test("sends question on Enter", async ({ page }) => {
  const sent = await mockChat(page, reply(200, FEE_ANSWER));

  await input(page).fill("¿Cuánto cuesta?");
  await input(page).press("Enter");

  await expect(page.getByTestId("answer")).toBeVisible();
  expect(sent).toEqual(["¿Cuánto cuesta?"]);
});

test("does not send blank question", async ({ page }) => {
  const sent = await mockChat(page, reply(200, FEE_ANSWER));

  await input(page).fill("   ");
  await input(page).press("Enter");
  await page.getByRole("button", { name: "Enviar" }).click();

  await page.waitForTimeout(300);
  expect(sent).toEqual([]);
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
  expect(sent).toEqual([SUGGESTIONS[3]]);
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
  await mockChat(page, reply(200, { answer: "<b>hola</b>", sources: [] }));

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
  await expect(suggestions(page)).toHaveCount(4);
});

test("does not send while an answer is pending", async ({ page }) => {
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  const sent = await mockChat(page, async (route) => {
    await held;
    await route.fulfill({ status: 200, json: FEE_ANSWER });
  });

  await input(page).fill("Primera");
  await input(page).press("Enter");
  await expect(page.getByRole("status")).toBeVisible();
  await page.getByRole("button", { name: SUGGESTIONS[0] }).click({ force: true });
  await input(page).fill("Segunda");
  await input(page).press("Enter");
  release();

  await expect(page.getByTestId("answer")).toBeVisible();
  expect(sent).toEqual(["Primera"]);
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
