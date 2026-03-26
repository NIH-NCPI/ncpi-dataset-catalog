import { expect, test } from "@playwright/test";

import { SEARCH_INPUT, TABLE_BODY, waitForResults } from "./helpers";

test.describe("Example Queries page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/example-queries");
  });

  test("header navigation contains Example Queries link", async ({ page }) => {
    const navLink = page.getByRole("link", { name: "Example Queries" });
    await expect(navLink).toBeVisible();
  });

  test("page renders all six dimension sections", async ({ page }) => {
    await expect(
      page.locator("h2", { hasText: "Study metadata" })
    ).toBeVisible();
    await expect(
      page.locator("h2", { hasText: "Harmonized variables" })
    ).toBeVisible();
    await expect(
      page.locator("h2", { hasText: "MeSH disease hierarchy" })
    ).toBeVisible();
    await expect(
      page.locator("h2", { hasText: "Consent codes" })
    ).toBeVisible();
    await expect(
      page.locator("h2", { hasText: "Inferred ancestry" })
    ).toBeVisible();
    await expect(page.locator("h2", { hasText: "Demographics" })).toBeVisible();
  });

  test("query chip submits its query and navigates to research page with results", async ({
    page,
  }) => {
    const chip = page.locator('button[type="submit"][data-query]').first();
    await expect(chip).toBeVisible();

    const queryText = await chip.getAttribute("data-query");
    expect(queryText).not.toBeNull();

    await chip.click();

    await page.waitForURL(/\/research\/studies/);
    await page.locator(SEARCH_INPUT).waitFor({ state: "visible" });
    await waitForResults(page);

    // Verify the chip's query text appears on the research page.
    await expect(page.locator("main")).toContainText(queryText as string);

    const tab = page.getByRole("tab", { name: /Results \(\d+\)/ });
    await expect(tab).toBeVisible();

    await expect(page.locator(TABLE_BODY)).toBeVisible();
  });
});
