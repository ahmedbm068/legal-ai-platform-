import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.PLAYWRIGHT_FRONTEND_PORT || 5175);
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || `http://localhost:${PORT}`;

/**
 * Frontend end-to-end suite.
 *
 * Run locally:
 *   1. Start the backend: `uvicorn backend.main:app --reload`
 *   2. Run the suite:    `npm run test:e2e --prefix frontend`
 *
 * The Vite dev server is started/stopped automatically via `webServer` so
 * tests boot from a clean state. The backend is NOT booted by Playwright
 * because it depends on Postgres/Redis/MinIO that are out of scope for an
 * e2e harness — we expect those running already (docker compose up).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: `npm run dev -- --port ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
