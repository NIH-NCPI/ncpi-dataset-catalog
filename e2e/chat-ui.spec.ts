import { expect, test } from "@playwright/test";

import {
  FILTER_CHIP,
  SEARCH_INPUT,
  SUBMIT_BUTTON,
  submitQuery,
  TABLE_BODY,
  waitForResults,
} from "./helpers";

test.describe("Chat UI", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/research/studies");
    await page.locator(SEARCH_INPUT).waitFor({ state: "visible" });
  });

  test("suggestion chip submits a query and returns results", async ({
    page,
  }) => {
    const suggestionChip = page.locator('button[type="submit"][data-query]');
    await expect(suggestionChip.first()).toBeVisible();

    const queryText = await suggestionChip.first().getAttribute("data-query");
    expect(queryText).not.toBeNull();

    await suggestionChip.first().click();
    await waitForResults(page);

    await expect(page.locator("main")).toContainText(queryText as string);

    const tab = page.getByRole("tab", { name: /Results \(\d+\)/ });
    await expect(tab).toBeVisible();
  });

  test("clicking a study row navigates to study detail", async ({ page }) => {
    await submitQuery(page, "type 1 diabetes studies on AnVIL");
    await waitForResults(page);

    await expect(page.locator(TABLE_BODY)).toBeVisible();

    const studyLink = page.locator(TABLE_BODY).getByRole("link").first();
    await expect(studyLink).toBeVisible();
    const href = await studyLink.getAttribute("href");
    expect(href).toMatch(/\/research\/studies\/phs/);

    await studyLink.click();
    await page.waitForURL(/\/research\/studies\/phs/);
  });

  test("placeholder updates after first query", async ({ page }) => {
    const input = page.locator(SEARCH_INPUT);

    await expect(input).toHaveAttribute(
      "placeholder",
      "Search for studies or variables"
    );

    await submitQuery(page, "diabetes studies on AnVIL");
    await waitForResults(page);

    await expect(input).toHaveAttribute("placeholder", /[Rr]efine/);
  });

  test("conversation history shows all messages", async ({ page }) => {
    await submitQuery(page, "diabetes studies on BDC");
    await waitForResults(page);

    await submitQuery(page, "also with BMI data");
    await waitForResults(page);

    const chatArea = page.locator("main");

    await expect(chatArea.getByText("diabetes studies on BDC")).toBeVisible();
    await expect(chatArea.getByText("also with BMI data")).toBeVisible();

    // Both queries should have produced assistant responses containing "Found".
    const assistantResponses = chatArea.locator(
      ':text-matches("Found \\\\d+")'
    );
    expect(await assistantResponses.count()).toBeGreaterThanOrEqual(2);
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

    await input.fill("");
    await page.locator(SUBMIT_BUTTON).click();

    await expect(input).toBeEnabled();
    expect(await page.locator(FILTER_CHIP).count()).toBe(0);

    const tab = page.getByRole("tab", { name: /Results \(\d+\)/ });
    await expect(tab).not.toBeVisible();
  });
});
