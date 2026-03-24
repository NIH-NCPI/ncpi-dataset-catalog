import { expect, Page, test } from "@playwright/test";

const SEARCH_INPUT = 'textarea[name="ai-prompt"]';
const SUBMIT_BUTTON = '.MuiIconButton-root[type="submit"]';
const RESULTS_HEADING = "h1";
const TABLE_BODY = ".MuiTableBody-root";
const FILTER_CHIP = ".MuiChip-root:has(.MuiChip-deleteIcon)";

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

  test("results include a summary message", async ({ page }) => {
    await submitQuery(page, "diabetes studies on AnVIL");
    await waitForResults(page);

    const heading = page.locator(RESULTS_HEADING);
    await expect(heading).toBeVisible();
    const tab = page.getByRole("tab", { name: /Results/ });
    await expect(tab).toBeVisible();
  });
});
