import { defineConfig, devices } from "@playwright/test";

// The backend is never called: every test intercepts POST /api/chat/stream with page.route.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  // ponytail: capped; one Chromium per CPU starves a Windows laptop and page loads time out.
  workers: 2,
  // Sandbox on locally as a second line of defence; off in CI, where tests load only this app on an
  // ephemeral runner with no secrets, and Ubuntu's AppArmor may block the sandbox.
  use: { baseURL: "http://127.0.0.1:3100", locale: "es-AR", launchOptions: { chromiumSandbox: !process.env.CI } },
  projects: [
    { name: "phone", use: { ...devices["Desktop Chrome"], viewport: { width: 375, height: 800 } } },
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
  ],
  // Production build on its own port: fast, deterministic, and independent of a running `npm run dev`.
  // 127.0.0.1, not localhost: on Windows localhost tries IPv6 first and page loads stall.
  webServer: {
    command: "npm run build && npx next start --hostname 127.0.0.1 --port 3100",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: false,
    timeout: 180_000,
  },
});
