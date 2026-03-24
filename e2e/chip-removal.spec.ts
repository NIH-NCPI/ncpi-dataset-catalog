import { expect, Page, test } from "@playwright/test";

const SEARCH_INPUT = 'textarea[name="ai-prompt"]';
const SUBMIT_BUTTON = '.MuiIconButton-root[type="submit"]';
const FILTER_CHIP = ".MuiChip-root:has(.MuiChip-deleteIcon)";
const CHIP_DELETE = ".MuiChip-deleteIcon";
const TABLE_BODY = ".MuiTableBody-root";

/**
 * Submits a search query on the research page.
 * @param page - Playwright page.
 * @param query - Query text to submit.
 */
async function submitQuery(page: Page, query: string): Promise<void> {
  const input = page.locator(SEARCH_INPUT);
  await input.click();
  await input.fill(query);
  await page.locator(SUBMIT_BUTTON).click();
}

/**
 * Waits for search results to settle by watching the input disabled state.
 * @param page - Playwright page.
 */
async function waitForResults(page: Page): Promise<void> {
  const input = page.locator(SEARCH_INPUT);
  // Wait for loading to start (input becomes disabled).
  await expect(input)
    .toBeDisabled({ timeout: 5_000 })
    .catch(() => {});
  // Wait for loading to finish (input becomes enabled).
  await expect(input).toBeEnabled({ timeout: 60_000 });
}

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

    // Expect no results with this over-constrained query.
    await expect(page.getByText("No results found.")).toBeVisible();

    // Expect at least 2 chips (focus + platform).
    const chips = page.locator(FILTER_CHIP);
    expect(await chips.count()).toBeGreaterThanOrEqual(2);

    // Remove the platform chip (KFDRC) to broaden the search.
    const platformChip = chips.filter({ hasText: /KFDRC/ });
    await expect(platformChip).toBeVisible();
    await platformChip.locator(CHIP_DELETE).click();
    await waitForResults(page);

    // With the platform constraint removed, results should appear.
    await expect(page.locator(TABLE_BODY)).toBeVisible();
    await expect(page.getByText("No results found.")).not.toBeVisible();
  });

  test("removing focus chip broadens results", async ({ page }) => {
    await submitQuery(page, "type 1 diabetes studies on AnVIL");
    await waitForResults(page);

    // Should find the 1 matching study.
    await expect(page.locator(TABLE_BODY)).toBeVisible();
    const tab = page.getByRole("tab", { name: /Results/ });
    const initialLabel = await tab.innerText();

    // Remove the focus/disease chip to broaden to all AnVIL studies.
    const chips = page.locator(FILTER_CHIP);
    const focusChip = chips.filter({ hasText: /Diabetes/ });
    await expect(focusChip).toBeVisible();
    await focusChip.locator(CHIP_DELETE).click();
    await waitForResults(page);

    // With focus removed, should have more results than before.
    await expect(page.locator(TABLE_BODY)).toBeVisible();
    const afterLabel = await tab.innerText();
    expect(afterLabel).not.toBe(initialLabel);
  });
});
