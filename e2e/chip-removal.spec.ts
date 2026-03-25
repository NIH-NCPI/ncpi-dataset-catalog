import { expect, test } from "@playwright/test";

import {
  FILTER_CHIP,
  SEARCH_INPUT,
  submitQuery,
  TABLE_BODY,
  waitForResults,
} from "./helpers";

const CHIP_DELETE = ".MuiChip-deleteIcon";

test.describe("Filter chip removal", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/research/studies");
    await page.locator(SEARCH_INPUT).waitFor({ state: "visible" });
  });

  // Type 1 Diabetes exists on AnVIL (1 study) but NOT on KFDRC (0 studies).
  // Querying for the combination should yield 0 results.
  // Removing the KFDRC platform chip should broaden results to include AnVIL.
  test("removing over-constraining chip reveals results", async ({ page }) => {
    await submitQuery(page, "type 1 diabetes studies on KFDRC");
    await waitForResults(page);

    await expect(page.getByText("No results found.")).toBeVisible();

    const chips = page.locator(FILTER_CHIP);
    expect(await chips.count()).toBeGreaterThanOrEqual(2);

    const platformChip = chips.filter({ hasText: /KFDRC/ });
    await expect(platformChip).toBeVisible();
    await platformChip.locator(CHIP_DELETE).click();
    await waitForResults(page);

    await expect(page.locator(TABLE_BODY)).toBeVisible();
    await expect(page.getByText("No results found.")).not.toBeVisible();
  });

  test("removing focus chip broadens results", async ({ page }) => {
    await submitQuery(page, "type 1 diabetes studies on AnVIL");
    await waitForResults(page);

    await expect(page.locator(TABLE_BODY)).toBeVisible();
    const tab = page.getByRole("tab", { name: /Results/ });
    const initialLabel = await tab.innerText();

    const chips = page.locator(FILTER_CHIP);
    const focusChip = chips.filter({ hasText: /Diabetes/ });
    await expect(focusChip).toBeVisible();
    await focusChip.locator(CHIP_DELETE).click();
    await waitForResults(page);

    await expect(page.locator(TABLE_BODY)).toBeVisible();
    const afterLabel = await tab.innerText();
    expect(afterLabel).not.toBe(initialLabel);
  });
});
