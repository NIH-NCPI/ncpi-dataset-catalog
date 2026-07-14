/**
 * SSG output-shape guardrail.
 *
 * Asserts on the HTML emitted by `next build` into `out/`, locking in the
 * CURRENT output shape so the staged restoration of server-rendered HTML is
 * verifiable. Today every route is statically exported with an empty
 * `<div id="__next"></div>` because `pages/_app.tsx` gates the whole tree
 * behind a client-side entities fetch — the failure mode is blank HTML, not a
 * crash, so without these assertions a regression looks identical to success.
 *
 * The asymmetry encoded below is deliberate:
 * - `/studies` is EXPECTED to remain a blank shell permanently — it is an
 *   interactive table behind a client-side fetch. Do not "fix" it.
 * - `/`, `/platforms` and `/research/studies/*` are blank only until the
 *   `_app` entities gate is deleted, which flips them to server-rendered HTML.
 *
 * Each later stage flips exactly one expectation here:
 * - studies list moves to client-side fetch: `/studies` HTML byte budget
 *   multi-MB → small
 * - `_app` entities gate deleted: `/`, `/platforms` and `/research/studies/*`
 *   body → RENDERED
 */
import fsp from "fs/promises";
import path from "path";

const BODY_EXPECTATION = {
  BLANK: "BLANK",
  RENDERED: "RENDERED",
} as const;

type BodyExpectation = (typeof BODY_EXPECTATION)[keyof typeof BODY_EXPECTATION];

interface RouteExpectation {
  body: BodyExpectation;
  comment: string;
  maxBytes: number;
  minBytes: number;
  relPath: string;
}

interface StudyDetailTab {
  label: string;
  suffix: string;
}

const OUT_DIR = path.resolve(process.cwd(), "out");

/**
 * Marker emitted by the Next.js pages router around the app's rendered HTML.
 * A blank page renders the open and close tags with nothing between them.
 */
const NEXT_ROOT_OPEN = '<div id="__next">';
const NEXT_ROOT_BLANK = '<div id="__next"></div>';

/**
 * Byte budgets (see epic #425). The windows are categorical, not precise:
 * blank shells are a few KB of head + `__NEXT_DATA__`; `/studies` bakes the
 * full studies list (~17.3 MB today) into `__NEXT_DATA__`; `/platforms` bakes
 * the platforms list (~0.5 MB). They are wide enough that routine catalog
 * data refreshes never trip them, while still distinguishing "multi-MB baked
 * payload" from "small shell" — the flip each later stage must make
 * deliberately.
 */
const BLANK_SHELL_MAX_BYTES = 50_000;
const PLATFORMS_HTML_MIN_BYTES = 200_000;
const PLATFORMS_HTML_MAX_BYTES = 1_500_000;
const STUDIES_HTML_MIN_BYTES = 10_000_000;
const STUDIES_HTML_MAX_BYTES = 30_000_000;

/**
 * A known dbGaP id with variables and selected-publications subpages, used to
 * spot-check the 8,832 prerendered study detail routes. If this study is ever
 * dropped from the catalog, swap in any other id present in
 * `catalog/ncpi-platform-studies.json`.
 */
const KNOWN_STUDY_ID = "phs000220";

const STUDY_DETAIL_TABS: StudyDetailTab[] = [
  { label: "overview", suffix: ".html" },
  { label: "variables tab", suffix: "/variables.html" },
  { label: "selected-publications tab", suffix: "/selected-publications.html" },
];

/**
 * Builds the blank-shell expectation for one study detail tab.
 * @param tab - Study detail tab to build the expectation for.
 * @returns Route expectation for the tab.
 */
function buildStudyDetailExpectation(tab: StudyDetailTab): RouteExpectation {
  return {
    body: BODY_EXPECTATION.BLANK,
    comment: `study detail ${tab.label} — blank until the _app gate is deleted`,
    maxBytes: BLANK_SHELL_MAX_BYTES,
    minBytes: 0,
    relPath: `research/studies/${KNOWN_STUDY_ID}${tab.suffix}`,
  };
}

const ROUTE_EXPECTATIONS: RouteExpectation[] = [
  {
    body: BODY_EXPECTATION.BLANK,
    comment: "homepage — blank until the _app entities gate is deleted",
    maxBytes: BLANK_SHELL_MAX_BYTES,
    minBytes: 0,
    relPath: "index.html",
  },
  {
    body: BODY_EXPECTATION.BLANK,
    comment:
      "studies list — blank body is PERMANENT (interactive table, client fetch); " +
      "the multi-MB __NEXT_DATA__ budget flips to small when the list moves to a client-side fetch",
    maxBytes: STUDIES_HTML_MAX_BYTES,
    minBytes: STUDIES_HTML_MIN_BYTES,
    relPath: "studies.html",
  },
  {
    body: BODY_EXPECTATION.BLANK,
    comment:
      "platforms list — control route; already small, blank until the _app gate is deleted",
    maxBytes: PLATFORMS_HTML_MAX_BYTES,
    minBytes: PLATFORMS_HTML_MIN_BYTES,
    relPath: "platforms.html",
  },
  ...STUDY_DETAIL_TABS.map(buildStudyDetailExpectation),
];

/**
 * Asserts a single route's emitted HTML matches its expectation.
 * @param expectation - Route expectation to verify.
 * @returns Error messages for the route; empty when the route passes.
 */
async function verifyRoute(expectation: RouteExpectation): Promise<string[]> {
  const { body, comment, maxBytes, minBytes, relPath } = expectation;
  const errors: string[] = [];
  const filePath = path.join(OUT_DIR, relPath);
  let html: Buffer;
  try {
    html = await fsp.readFile(filePath);
  } catch (error) {
    const { code } = error as NodeJS.ErrnoException;
    return code === "ENOENT"
      ? [`${relPath}: file not found (${comment})`]
      : [`${relPath}: failed to read file — ${String(error)} (${comment})`];
  }
  if (html.length < minBytes || html.length > maxBytes) {
    errors.push(
      `${relPath}: ${html.length} bytes is outside budget [${minBytes}, ${maxBytes}] (${comment})`
    );
  }
  if (!html.includes(NEXT_ROOT_OPEN)) {
    errors.push(`${relPath}: no ${NEXT_ROOT_OPEN} root found (${comment})`);
  } else if (body === BODY_EXPECTATION.BLANK) {
    if (!html.includes(NEXT_ROOT_BLANK)) {
      errors.push(
        `${relPath}: expected a blank body (exactly ${NEXT_ROOT_BLANK}) but found rendered content (${comment})`
      );
    }
  } else if (html.includes(NEXT_ROOT_BLANK)) {
    errors.push(
      `${relPath}: expected rendered body content but found ${NEXT_ROOT_BLANK} (${comment})`
    );
  }
  return errors;
}

/**
 * Verifies every route expectation against the build output and exits
 * non-zero when any assertion fails.
 * @returns Promise that resolves when verification completes.
 */
async function verifySsgOutput(): Promise<void> {
  const errors = (
    await Promise.all(ROUTE_EXPECTATIONS.map(verifyRoute))
  ).flat();
  if (errors.length > 0) {
    console.error("SSG output-shape guardrail failed:");
    for (const error of errors) console.error(`  - ${error}`);
    process.exit(1);
  }
  console.log(
    `SSG output-shape guardrail passed (${ROUTE_EXPECTATIONS.length} routes checked).`
  );
}

verifySsgOutput().catch((error) => {
  console.error("SSG output-shape guardrail crashed:", error);
  process.exit(1);
});
