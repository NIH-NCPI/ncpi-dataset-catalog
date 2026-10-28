import {
  expect,
  type Locator,
  type Page,
  type Response,
} from "@playwright/test";

export const SEARCH_INPUT = 'textarea[name="ai-prompt"]';
export const FILTER_CHIP = ".MuiChip-root:has(.MuiChip-deleteIcon)";
export const TABLE_BODY = ".MuiTableBody-root";

const SEARCH_PATH = /\/search(\/filter)?$/;

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
 * Returns true if the response is to a search request: a POST to the search
 * API (`/search`) or its filter-removal endpoint (`/search/filter`).
 * @param response - Playwright response.
 * @returns True if the response is a search response.
 */
function isSearchResponse(response: Response): boolean {
  return (
    response.request().method() === "POST" &&
    SEARCH_PATH.test(new URL(response.url()).pathname)
  );
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
 * Runs an action that triggers a search, then waits for the search to complete:
 * its response is received and the submit button, disabled while a query is in
 * flight, is re-enabled. The response is awaited rather than the button's
 * disabled state, which a fast response (e.g. a filter-chip removal) can clear
 * before it is observed. Fails if the action never sends a search.
 * @param page - Playwright page.
 * @param action - Action that triggers the search, e.g. submitting a query.
 */
export async function waitForResults(
  page: Page,
  action: () => Promise<unknown>
): Promise<void> {
  // Register before the action so a fast response is not missed.
  const response = page.waitForResponse(isSearchResponse, {
    timeout: 60_000,
  });
  await action();
  await response;
  await expect(getSubmitButton(page)).toBeEnabled({ timeout: 60_000 });
}
