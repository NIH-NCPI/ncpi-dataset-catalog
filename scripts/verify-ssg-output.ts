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
 *   interactive table behind a client-side fetch of its apiPath JSON. Do not
 *   "fix" it.
 * - `/studies/<id>` pages must keep baking the study into `__NEXT_DATA__`
 *   (props.data feeds the detail view statically); `/research/studies/<id>`
 *   pages carry no baked study — the view reads the workflows store.
 * - `/`, `/platforms`, `/studies/<id>` and `/research/studies/<id>` are blank
 *   only until the `_app` entities gate is deleted, which flips them to
 *   server-rendered HTML.
 *
 * The remaining stage flips one expectation here:
 * - `_app` entities gate deleted: `/`, `/platforms`, `/studies/<id>` and
 *   `/research/studies/<id>` body → RENDERED
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

interface StudyDetailFamily {
  comment: string;
  maxBytes: number;
  minBytes: number;
  pathPrefix: string;
}

interface StudyDetailTab {
  label: string;
  suffix: string;
}

const OUT_DIR = path.resolve(process.cwd(), "out");

/**
 * Marker emitted by the Next.js pages router around the app's rendered HTML.
 * A blank page renders nothing but whitespace or comments between the open
 * tag and its closing `</div>`.
 */
const NEXT_ROOT_OPEN = '<div id="__next">';

/**
 * How many bytes after the root div open tag are inspected when classifying
 * the body as blank vs rendered, and how much of it is quoted in failure
 * messages.
 */
const ROOT_WINDOW_BYTES = 512;
const ROOT_SNIPPET_LENGTH = 80;

/**
 * Byte budgets (see epic #425). The windows are categorical, not precise:
 * blank shells are a few KB of head + `__NEXT_DATA__`; `/studies` no longer
 * bakes the studies list (fetched at runtime from its apiPath); `/studies/<id>`
 * bakes one study (~24 KB) into `__NEXT_DATA__`; `/platforms` bakes the
 * platforms list (~0.5 MB). They are wide enough that routine catalog data
 * refreshes never trip them, while still distinguishing "baked payload" from
 * "small shell" — any flip must be made deliberately.
 */
const BLANK_SHELL_MAX_BYTES = 50_000;
const PLATFORMS_HTML_MIN_BYTES = 200_000;
const PLATFORMS_HTML_MAX_BYTES = 1_500_000;
const STUDY_DETAIL_HTML_MIN_BYTES = 10_000;
const STUDY_DETAIL_HTML_MAX_BYTES = 150_000;

/**
 * The studies list JSON served at runtime (the studies entity's apiPath,
 * copied into the export by scripts/sync-api.sh). It is now the sole source
 * of the studies list, so the export must contain it — a broken artifact
 * pipeline would otherwise stay green while the deployed list fails its
 * runtime fetch. The size window flips to small when the list JSON is
 * slimmed (see epic #425).
 */
const LIST_ARTIFACT_REL_PATH = "api/ncpi-platform-studies.json";
const LIST_ARTIFACT_MIN_BYTES = 10_000_000;
const LIST_ARTIFACT_MAX_BYTES = 40_000_000;

/**
 * A known dbGaP id with variables and selected-publications subpages, used to
 * spot-check both prerendered study detail route families (`/studies/<id>`
 * and `/research/studies/<id>`, 8,832 paths each). If this study is ever
 * dropped from the catalog, swap in any other id present in
 * `catalog/ncpi-platform-studies.json`.
 */
const KNOWN_STUDY_ID = "phs000220";

/**
 * The two prerendered study detail route families:
 * - `/research/studies/<id>` carries no baked study — the view reads the
 *   workflows store client-side — so it is a plain blank shell.
 * - `/studies/<id>` is linked from the studies list and must keep baking the
 *   study into `__NEXT_DATA__` (props.data feeds the detail view statically);
 *   hence its minimum byte budget.
 */
const STUDY_DETAIL_FAMILIES: StudyDetailFamily[] = [
  {
    comment: "research study detail — blank until the _app gate is deleted",
    maxBytes: BLANK_SHELL_MAX_BYTES,
    minBytes: 0,
    pathPrefix: "research/studies/",
  },
  {
    comment:
      "list-linked study detail — blank until the _app gate is deleted; must bake the study into __NEXT_DATA__",
    maxBytes: STUDY_DETAIL_HTML_MAX_BYTES,
    minBytes: STUDY_DETAIL_HTML_MIN_BYTES,
    pathPrefix: "studies/",
  },
];

const STUDY_DETAIL_TABS: StudyDetailTab[] = [
  { label: "overview", suffix: ".html" },
  { label: "variables tab", suffix: "/variables.html" },
  { label: "selected-publications tab", suffix: "/selected-publications.html" },
];

/**
 * Builds the expectation for one study detail tab of the given route family.
 * @param family - Study detail route family to build the expectation for.
 * @param tab - Study detail tab to build the expectation for.
 * @returns Route expectation for the tab.
 */
function buildStudyDetailExpectation(
  family: StudyDetailFamily,
  tab: StudyDetailTab
): RouteExpectation {
  return {
    body: BODY_EXPECTATION.BLANK,
    comment: `${family.comment} (${tab.label})`,
    maxBytes: family.maxBytes,
    minBytes: family.minBytes,
    relPath: `${family.pathPrefix}${KNOWN_STUDY_ID}${tab.suffix}`,
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
      "studies list — blank body is PERMANENT (interactive table, client-side " +
      "fetch of the apiPath JSON); the list must NOT be baked into __NEXT_DATA__",
    maxBytes: BLANK_SHELL_MAX_BYTES,
    minBytes: 0,
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
  ...STUDY_DETAIL_FAMILIES.flatMap((family) =>
    STUDY_DETAIL_TABS.map((tab) => buildStudyDetailExpectation(family, tab))
  ),
];

/**
 * Classifies the content following the root div open tag as blank.
 * @param rootContent - Content immediately following the root div open tag.
 * @returns True when the root div holds nothing but whitespace or comments.
 */
function isBlankRootContent(rootContent: string): boolean {
  const content = rootContent.replace(/^(\s|<!--[\s\S]*?-->)*/, "");
  return content.startsWith("</div>");
}

/**
 * Asserts the runtime studies-list JSON artifact exists in the export within
 * its byte budget.
 * @returns Error messages for the artifact; empty when it passes.
 */
async function verifyListArtifact(): Promise<string[]> {
  const filePath = path.join(OUT_DIR, LIST_ARTIFACT_REL_PATH);
  let byteLength: number;
  try {
    byteLength = (await fsp.stat(filePath)).size;
  } catch {
    return [
      `${LIST_ARTIFACT_REL_PATH}: missing — the studies list has no runtime data source`,
    ];
  }
  if (
    byteLength < LIST_ARTIFACT_MIN_BYTES ||
    byteLength > LIST_ARTIFACT_MAX_BYTES
  ) {
    return [
      `${LIST_ARTIFACT_REL_PATH}: ${byteLength} bytes is outside budget [${LIST_ARTIFACT_MIN_BYTES}, ${LIST_ARTIFACT_MAX_BYTES}]`,
    ];
  }
  return [];
}

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
  const rootIndex = html.indexOf(NEXT_ROOT_OPEN);
  if (rootIndex === -1) {
    errors.push(`${relPath}: no ${NEXT_ROOT_OPEN} root found (${comment})`);
    return errors;
  }
  const contentStart = rootIndex + NEXT_ROOT_OPEN.length;
  const rootContent = html
    .subarray(contentStart, contentStart + ROOT_WINDOW_BYTES)
    .toString("utf8");
  const isBlank = isBlankRootContent(rootContent);
  if (body === BODY_EXPECTATION.BLANK && !isBlank) {
    const snippet = JSON.stringify(rootContent.slice(0, ROOT_SNIPPET_LENGTH));
    errors.push(
      `${relPath}: expected a blank ${NEXT_ROOT_OPEN} body but found content starting with ${snippet} (${comment})`
    );
  } else if (body === BODY_EXPECTATION.RENDERED && isBlank) {
    errors.push(
      `${relPath}: expected rendered body content but the ${NEXT_ROOT_OPEN} root is blank (${comment})`
    );
  }
  return errors;
}

/**
 * Verifies every route expectation against the build output and sets a
 * non-zero exit code when any assertion fails. Uses `process.exitCode` rather
 * than `process.exit()` so queued stderr writes flush before the process
 * ends (stdio is asynchronous when piped, as in CI).
 * @returns Promise that resolves when verification completes.
 */
async function verifySsgOutput(): Promise<void> {
  const errors = (
    await Promise.all([
      ...ROUTE_EXPECTATIONS.map(verifyRoute),
      verifyListArtifact(),
    ])
  ).flat();
  if (errors.length > 0) {
    console.error("SSG output-shape guardrail failed:");
    for (const error of errors) console.error(`  - ${error}`);
    process.exitCode = 1;
    return;
  }
  console.log(
    `SSG output-shape guardrail passed (${ROUTE_EXPECTATIONS.length} routes + list artifact checked).`
  );
}

verifySsgOutput().catch((error) => {
  console.error("SSG output-shape guardrail crashed:", error);
  process.exitCode = 1;
});
