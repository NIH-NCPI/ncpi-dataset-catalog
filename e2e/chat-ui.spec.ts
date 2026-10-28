import { expect, test } from "@playwright/test";

import {
  FILTER_CHIP,
  getResultsTab,
  getSubmitButton,
  SEARCH_INPUT,
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

    await waitForResults(page, () => suggestionChip.first().click());

    await expect(page.locator("main")).toContainText(queryText as string);

    const tab = getResultsTab(page);
    await expect(tab).toBeVisible();
  });

  test("clicking a study row navigates to study detail", async ({ page }) => {
    await waitForResults(page, () =>
      submitQuery(page, "type 1 diabetes studies on AnVIL")
    );

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

    await waitForResults(page, () =>
      submitQuery(page, "diabetes studies on AnVIL")
    );

    await expect(input).toHaveAttribute("placeholder", /[Rr]efine/);
  });

  test("conversation history shows all messages", async ({ page }) => {
    // The results count comes from the response data, unlike the assistant's
    // LLM-written summary, so it is a stable signal that each turn completed.
    const tab = getResultsTab(page);

    await waitForResults(page, () =>
      submitQuery(page, "diabetes studies on BDC")
    );
    await expect(tab).toBeVisible();

    await waitForResults(page, () => submitQuery(page, "also with BMI data"));
    await expect(tab).toBeVisible();

    // Exact match: the assistant's summary may echo the query text.
    const chatArea = page.locator("main");

    await expect(
      chatArea.getByText("diabetes studies on BDC", { exact: true })
    ).toBeVisible();
    await expect(
      chatArea.getByText("also with BMI data", { exact: true })
    ).toBeVisible();
  });

  test("download TSV button triggers a download", async ({ page }) => {
    await waitForResults(page, () =>
      submitQuery(page, "diabetes studies on AnVIL")
    );

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
    const submitButton = getSubmitButton(page);

    await page.locator(SEARCH_INPUT).fill("");
    await submitButton.click();

    await expect(submitButton).toBeEnabled();
    expect(await page.locator(FILTER_CHIP).count()).toBe(0);

    const tab = getResultsTab(page);
    await expect(tab).not.toBeVisible();
  });
});
