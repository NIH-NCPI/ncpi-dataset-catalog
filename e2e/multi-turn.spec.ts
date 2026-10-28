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
    await waitForResults(page, () =>
      submitQuery(page, "diabetes studies on AnVIL")
    );

    await waitForResults(page, () => submitQuery(page, "also include BDC"));

    const chipsAfter = await getChipLabels(page);
    const afterText = chipsAfter.join(" ").toLowerCase();

    expect(afterText).toContain("bdc");
    expect(chipsAfter.length).toBeGreaterThan(0);
  });

  test("follow-up preserves study intent when adding criteria", async ({
    page,
  }) => {
    await waitForResults(page, () =>
      submitQuery(page, "studies with transcriptomic data on diabetes")
    );

    const headingBefore = page.locator("h1").first();
    await expect(headingBefore).toHaveText("Studies");

    await waitForResults(page, () =>
      submitQuery(page, "also where BMI was measured")
    );

    const headingAfter = page.locator("h1").first();
    await expect(headingAfter).toHaveText("Studies");
  });

  test("follow-up replaces a filter", async ({ page }) => {
    await waitForResults(page, () =>
      submitQuery(page, "cancer studies on AnVIL")
    );

    await waitForResults(page, () =>
      submitQuery(page, "change cancer to diabetes")
    );

    const chipsAfter = await getChipLabels(page);
    const afterText = chipsAfter.join(" ").toLowerCase();

    expect(afterText).toContain("diabetes");
    expect(afterText).not.toContain("cancer");
  });
});
