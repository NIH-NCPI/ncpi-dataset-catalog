import { expect, type Locator, type Page } from "@playwright/test";

export const SEARCH_INPUT = 'textarea[name="ai-prompt"]';
export const FILTER_CHIP = ".MuiChip-root:has(.MuiChip-deleteIcon)";
export const TABLE_BODY = ".MuiTableBody-root";

/**
 * Returns the visible filter chip labels.
 * @param page - Playwright page.
 * @returns Array of chip label strings.
 */
export async function getChipLabels(page: Page): Promise<string[]> {
  return page.locator(FILTER_CHIP).allInnerTexts();
}

/**
 * Returns the results tab, once its label carries a count; the count is only
 * shown while the latest message is an assistant response with results.
 * @param page - Playwright page.
 * @returns Results tab locator.
 */
export function getResultsTab(page: Page): Locator {
  return page.getByRole("tab", { name: /Results \(\d+\)/ });
}

/**
 * Returns the prompt's "Send prompt" submit button.
 * @param page - Playwright page.
 * @returns Submit button locator.
 */
export function getSubmitButton(page: Page): Locator {
  return page.getByRole("button", { name: "Send prompt" });
}

/**
 * Submits a search query on the research page.
 * @param page - Playwright page.
 * @param query - Query text to submit.
 */
export async function submitQuery(page: Page, query: string): Promise<void> {
  const input = page.locator(SEARCH_INPUT);
  await input.click();
  await input.fill(query);
  await getSubmitButton(page).click();
}

/**
 * Waits for a search query to complete by observing the submit button's loading cycle.
 * The submit button is disabled while a query is in flight and re-enabled when done;
 * the input itself stays enabled throughout. A missed disabled state fails the
 * wait, since it means the query never started (search responses take seconds).
 * @param page - Playwright page.
 */
export async function waitForResults(page: Page): Promise<void> {
  const submitButton = getSubmitButton(page);
  await expect(submitButton).toBeDisabled({ timeout: 5_000 });
  await expect(submitButton).toBeEnabled({ timeout: 60_000 });
}
