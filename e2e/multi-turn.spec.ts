import { expect, test } from "@playwright/test";

import {
  getChipLabels,
  SEARCH_INPUT,
  submitQuery,
  waitForResults,
} from "./helpers";

test.describe("Multi-turn conversation", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/research/studies");
    await page.locator(SEARCH_INPUT).waitFor({ state: "visible" });
  });

  test("follow-up refines filters", async ({ page }) => {
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
