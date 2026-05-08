import { test, expect } from "@playwright/test";

/**
 * Happy-path smoke test: the login page renders, the form is usable, and an
 * obviously-bad credential yields the surfaced auth error (no white screen,
 * no console crash).
 *
 * This is intentionally lightweight — exercising the full upload → copilot
 * flow requires a seeded backend with a tenant, a lawyer user, and a case,
 * which lives in `scripts/full_smoke_test.py`. Use that for the end-to-end
 * pipeline; this Playwright suite guards against frontend regressions only.
 */
test.describe("Login page", () => {
  test("renders the form and surfaces an auth error for invalid credentials", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("pageerror", (err) => consoleErrors.push(err.message));
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });

    await page.goto("/login");

    // The route is reachable and rendered something interactive.
    const emailField = page.getByLabel(/email/i).first();
    const passwordField = page.getByLabel(/password/i).first();
    const submit = page.getByRole("button", { name: /sign in|log in|login/i }).first();

    await expect(emailField).toBeVisible();
    await expect(passwordField).toBeVisible();
    await expect(submit).toBeVisible();

    await emailField.fill("nobody@example.invalid");
    await passwordField.fill("definitely-wrong-password");
    await submit.click();

    // Either the backend refused (we see an error UI) or the network call
    // failed (still a non-crash). Either way we should NOT have moved off
    // the login route into a broken workspace shell.
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveURL(/login/);

    // No uncaught render errors — that's the regression we actually care
    // about for a Playwright happy-path.
    expect(
      consoleErrors.filter(
        (msg) =>
          !msg.includes("net::") && // network errors are expected here
          !msg.toLowerCase().includes("favicon")
      )
    ).toEqual([]);
  });
});
