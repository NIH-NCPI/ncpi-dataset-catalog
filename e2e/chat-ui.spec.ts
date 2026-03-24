import { expect, Page, test } from "@playwright/test";

const SEARCH_INPUT = 'textarea[name="ai-prompt"]';
const SUBMIT_BUTTON = '.MuiIconButton-root[type="submit"]';
const FILTER_CHIP = ".MuiChip-root:has(.MuiChip-deleteIcon)";
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
  await expect(input)
    .toBeDisabled({ timeout: 5_000 })
    .catch(() => {});
  await expect(input).toBeEnabled({ timeout: 60_000 });
}

test.describe("Chat UI", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/research/studies");
    await page.locator(SEARCH_INPUT).waitFor({ state: "visible" });
  });

  test("suggestion chip submits a query and returns results", async ({
    page,
  }) => {
    // Suggestion chips are submit buttons with a data-query attribute.
    const suggestionChip = page.locator('button[type="submit"][data-query]');
    await expect(suggestionChip.first()).toBeVisible();

    // The data-query attribute holds the actual query text shown in chat.
    const queryText = await suggestionChip.first().getAttribute("data-query");
    await suggestionChip.first().click();
    await waitForResults(page);

    // The query text should appear as a user message in the chat.
    await expect(page.locator("main")).toContainText(queryText!);

    // Results should render with a count.
    const tab = page.getByRole("tab", { name: /Results \(\d+\)/ });
    await expect(tab).toBeVisible();
  });

  test("clicking a study row navigates to study detail", async ({ page }) => {
    await submitQuery(page, "type 1 diabetes studies on AnVIL");
    await waitForResults(page);

    await expect(page.locator(TABLE_BODY)).toBeVisible();

    // Click the first study link in the results table.
    const studyLink = page.locator(TABLE_BODY).getByRole("link").first();
    await expect(studyLink).toBeVisible();
    const href = await studyLink.getAttribute("href");
    expect(href).toMatch(/\/research\/studies\/phs/);

    await studyLink.click();
    await page.waitForURL(/\/research\/studies\/phs/);
    expect(page.url()).toContain("/research/studies/phs");
  });

  test("placeholder updates after first query", async ({ page }) => {
    const input = page.locator(SEARCH_INPUT);

    // Initial placeholder.
    await expect(input).toHaveAttribute(
      "placeholder",
      "Ask about studies or variables"
    );

    await submitQuery(page, "diabetes studies on AnVIL");
    await waitForResults(page);

    // After results, placeholder should change to refine prompt.
    await expect(input).toHaveAttribute("placeholder", /[Rr]efine/);
  });

  test("conversation history shows all messages", async ({ page }) => {
    await submitQuery(page, "diabetes studies on AnVIL");
    await waitForResults(page);

    await submitQuery(page, "also include BDC");
    await waitForResults(page);

    const chatArea = page.locator("main");

    // Both user messages should be visible.
    await expect(chatArea.getByText("diabetes studies on AnVIL")).toBeVisible();
    await expect(chatArea.getByText("also include BDC")).toBeVisible();

    // Both assistant responses should be visible (contain "Found" or similar).
    // There should be at least 2 assistant message blocks.
    const assistantMessages = chatArea.locator(
      ':text-matches("Found|No results|studies")'
    );
    expect(await assistantMessages.count()).toBeGreaterThanOrEqual(2);
  });

  test("download TSV button triggers a download", async ({ page }) => {
    await submitQuery(page, "diabetes studies on AnVIL");
    await waitForResults(page);

    await expect(page.locator(TABLE_BODY)).toBeVisible();

    const downloadButton = page.getByRole("button", { name: /Download TSV/ });
    await expect(downloadButton).toBeVisible();

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      downloadButton.click(),
    ]);

    expect(download.suggestedFilename()).toMatch(/\.tsv$/);
  });

  test("empty query does not trigger a search", async ({ page }) => {
    const input = page.locator(SEARCH_INPUT);

    // Ensure input is empty and click submit.
    await input.fill("");
    await page.locator(SUBMIT_BUTTON).click();

    // Input should remain enabled (no loading triggered).
    await expect(input).toBeEnabled();

    // Wait briefly to confirm nothing happens.
    await page.waitForTimeout(1_000);

    // No filter chips should appear.
    expect(await page.locator(FILTER_CHIP).count()).toBe(0);

    // The results tab should not show a count.
    const tab = page.getByRole("tab", { name: /Results \(\d+\)/ });
    await expect(tab).not.toBeVisible();
  });
});
