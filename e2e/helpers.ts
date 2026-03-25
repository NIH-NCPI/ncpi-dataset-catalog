import { expect, Page } from "@playwright/test";

export const SEARCH_INPUT = 'textarea[name="ai-prompt"]';
export const SUBMIT_BUTTON = '.MuiIconButton-root[type="submit"]';
export const FILTER_CHIP = ".MuiChip-root:has(.MuiChip-deleteIcon)";
export const TABLE_BODY = ".MuiTableBody-root";

/**
 * Submits a search query on the research page.
 * @param page - Playwright page.
 * @param query - Query text to submit.
 */
export async function submitQuery(page: Page, query: string): Promise<void> {
  const input = page.locator(SEARCH_INPUT);
  await input.click();
  await input.fill(query);
  await page.locator(SUBMIT_BUTTON).click();
}

/**
 * Waits for a search query to complete by observing the input's loading cycle.
 * The input is disabled while a query is in flight and re-enabled when done.
 * @param page - Playwright page.
 */
export async function waitForResults(page: Page): Promise<void> {
  const input = page.locator(SEARCH_INPUT);
  // The disabled transition can be too fast to observe; ignore if missed.
  await expect(input)
    .toBeDisabled({ timeout: 5_000 })
    .catch(() => {});
  await expect(input).toBeEnabled({ timeout: 60_000 });
}

/**
 * Returns the visible filter chip labels.
 * @param page - Playwright page.
 * @returns Array of chip label strings.
 */
export async function getChipLabels(page: Page): Promise<string[]> {
  return page.locator(FILTER_CHIP).allInnerTexts();
}
