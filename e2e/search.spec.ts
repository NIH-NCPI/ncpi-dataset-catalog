import { expect, test } from "@playwright/test";

import {
  FILTER_CHIP,
  SEARCH_INPUT,
  submitQuery,
  TABLE_BODY,
  waitForResults,
} from "./helpers";

const RESULTS_HEADING = "h1";

test.describe("Core search flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/research/studies");
    await page.locator(SEARCH_INPUT).waitFor({ state: "visible" });
  });

  test("study search returns results table", async ({ page }) => {
    await submitQuery(page, "diabetes studies on AnVIL");
    await waitForResults(page);

    const heading = page.locator(RESULTS_HEADING).first();
    await expect(heading).toHaveText(/Studies|Variables/);

    const tableBody = page.locator(TABLE_BODY);
    await expect(tableBody).toBeVisible();
  });

  test("variable search returns results", async ({ page }) => {
    await submitQuery(page, "what variables measure blood pressure?");
    await waitForResults(page);

    const heading = page.locator(RESULTS_HEADING).first();
    await expect(heading).toHaveText(/Studies|Variables/);

    const tableBody = page.locator(TABLE_BODY);
    await expect(tableBody).toBeVisible();
  });

  test("filter chips render after query", async ({ page }) => {
    await submitQuery(page, "diabetes studies on AnVIL");
    await waitForResults(page);

    const chips = page.locator(FILTER_CHIP);
    await expect(chips.first()).toBeVisible();
    expect(await chips.count()).toBeGreaterThan(0);
  });

  test("zero results shows diagnostic message", async ({ page }) => {
    await submitQuery(
      page,
      "xyzzy nonexistent impossible query that matches nothing 12345"
    );
    await waitForResults(page);

    await expect(page.getByText("No results found.")).toBeVisible();
  });
});
