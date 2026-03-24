import { expect, Page, test } from "@playwright/test";

const SEARCH_INPUT = 'textarea[name="ai-prompt"]';
const SUBMIT_BUTTON = '.MuiIconButton-root[type="submit"]';
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

/**
 * Returns the visible filter chip labels.
 * @param page - Playwright page.
 * @returns Array of chip label strings.
 */
async function getChipLabels(page: Page): Promise<string[]> {
  const chips = page.locator(FILTER_CHIP);
  const count = await chips.count();
  const labels: string[] = [];
  for (let i = 0; i < count; i++) {
    labels.push(await chips.nth(i).innerText());
  }
  return labels;
}

test.describe("Multi-turn conversation", () => {
  test("follow-up refines filters", async ({ page }) => {
    await page.goto("/research/studies");
    await page.locator(SEARCH_INPUT).waitFor({ state: "visible" });

    await submitQuery(page, "diabetes studies on AnVIL");
    await waitForResults(page);

    await submitQuery(page, "also include BDC");
    await waitForResults(page);

    const chipsAfter = await getChipLabels(page);
    const afterText = chipsAfter.join(" ").toLowerCase();

    expect(afterText).toContain("bdc");
    expect(chipsAfter.length).toBeGreaterThan(0);
  });

  test("follow-up replaces a filter", async ({ page }) => {
    await page.goto("/research/studies");
    await page.locator(SEARCH_INPUT).waitFor({ state: "visible" });

    await submitQuery(page, "cancer studies on AnVIL");
    await waitForResults(page);

    await submitQuery(page, "change cancer to diabetes");
    await waitForResults(page);

    const chipsAfter = await getChipLabels(page);
    const afterText = chipsAfter.join(" ").toLowerCase();

    expect(afterText).toContain("diabetes");
    expect(afterText).not.toContain("cancer");
  });
});
