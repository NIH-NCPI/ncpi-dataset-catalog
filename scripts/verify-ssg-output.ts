/**
 * SSG output-shape guardrail.
 *
 * Asserts on the HTML emitted by `next build` into `out/`, locking in the
 * output shape so the staged restoration of server-rendered HTML stays
 * verifiable. Every route now server-renders: `pages/_app.tsx` no longer gates
 * the tree behind a client-side entities fetch, so a regression that reblanks a
 * route (e.g. reintroducing a client-side gate) fails the RENDERED assertion
 * below rather than looking identical to success.
 *
 * The byte budgets encode the remaining distinctions:
 * - `/studies` server-renders its interactive-table SHELL only — the list is
 *   fetched at runtime from its apiPath JSON and must NOT be baked into
 *   `__NEXT_DATA__` (its ceiling sits far below the list size to catch that).
 * - `/platforms` bakes the platforms list into `__NEXT_DATA__` (~0.5 MB).
 * - `/studies/<id>` bakes the full study (props.data); `/research/studies/<id>`
 *   bakes a per-tab slice of the study (props.study).
 * - `/` is presentational and bakes no entity payload.
 *
 * The remaining stage flips one expectation here:
 * - Stage 3b (#430): the runtime list JSON is slimmed, so
 *   LIST_ARTIFACT_MIN/MAX_BYTES shrinks from its current 10–40 MB window.
 */
import fsp from "fs/promises";
import path from "path";

const BODY_EXPECTATION = {
  BLANK: "BLANK",
  RENDERED: "RENDERED",
} as const;

type BodyExpectation = (typeof BODY_EXPECTATION)[keyof typeof BODY_EXPECTATION];

interface KnownStudy {
  id: string;
  note: string;
}

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
 * a rendered SHELL (the homepage, and the `/studies` table chrome with no baked
 * entity payload) is tens of KB; `/platforms` bakes the platforms list
 * (~0.5 MB); a study detail page bakes one study — see
 * STUDY_DETAIL_HTML_MAX_BYTES below. They are wide enough that routine catalog
 * data refreshes never trip them, while still distinguishing "baked payload"
 * from "shell" — in particular the shell ceiling sits far below the runtime
 * list size, so a `/studies` regression that bakes the list into the HTML trips
 * it. Any flip must be made deliberately.
 */
const SHELL_HTML_MIN_BYTES = 10_000;
const SHELL_HTML_MAX_BYTES = 150_000;
const PLATFORMS_HTML_MIN_BYTES = 200_000;
const PLATFORMS_HTML_MAX_BYTES = 1_500_000;
const STUDY_DETAIL_HTML_MIN_BYTES = 10_000;

/**
 * Both study detail route families bake the study's publication list into
 * `__NEXT_DATA__`: the list-linked `/studies/<id>` bakes the full study on
 * every tab (props.data), and `/research/studies/<id>` bakes it on the
 * selected-publications tab (props.study slice). That list dominates the page
 * size — a few KB for a typical study, but ~760 KB for the most-published study
 * (phs000209, 635 publications). This single ceiling covers both families: it
 * gives ~2x headroom over that worst case so refreshes that add publications
 * don't trip it, while staying ~16x below the 24 MB full catalog so a
 * regression that bakes the whole list into a page is still caught.
 */
const STUDY_DETAIL_HTML_MAX_BYTES = 1_500_000;

/**
 * The studies list JSON served at runtime (the studies entity's apiPath).
 * scripts/sync-api.sh copies it from catalog/ into public/api/, which Next then
 * includes in the export. It is now the sole source of the studies list, so the
 * export must contain it — a broken artifact pipeline would otherwise stay green
 * while the deployed list fails its runtime fetch. The size window flips to
 * small when the list JSON is slimmed (see epic #425).
 */
const LIST_ARTIFACT_REL_PATH = "api/ncpi-platform-studies.json";
const LIST_ARTIFACT_MIN_BYTES = 10_000_000;
const LIST_ARTIFACT_MAX_BYTES = 40_000_000;

/**
 * dbGaP ids with variables and selected-publications subpages, spot-checked
 * across both prerendered study detail route families (`/studies/<id>` and
 * `/research/studies/<id>`, 8,832 paths each). Two are checked so the budget is
 * exercised at both ends: phs000220 is a typical small study, and phs000209 is
 * the most-published study in the catalog (635 publications, ~760 KB) that
 * STUDY_DETAIL_HTML_MAX_BYTES was sized against — without it the ceiling is
 * never actually tested, so a regression that bloats heavy studies would pass.
 * If either is dropped from the catalog, swap in another id present in
 * `catalog/ncpi-platform-studies.json` (a small study, and the heaviest by
 * publication count, respectively).
 */
const KNOWN_STUDY_IDS: KnownStudy[] = [
  { id: "phs000220", note: "typical study" },
  { id: "phs000209", note: "heaviest study — 635 publications, ~760 KB" },
];

/**
 * The two prerendered study detail route families, both server-rendered and
 * both bounded by STUDY_DETAIL_HTML_MAX_BYTES (the baked publication list
 * dominates either way):
 * - `/research/studies/<id>` bakes a per-tab slice of the study into
 *   `__NEXT_DATA__` (a few KB per tab; the selected-publications slice carries
 *   the full publication list).
 * - `/studies/<id>` is linked from the studies list and bakes the full study
 *   into `__NEXT_DATA__` on every tab (props.data feeds the detail view
 *   statically).
 */
const STUDY_DETAIL_FAMILIES: StudyDetailFamily[] = [
  {
    comment:
      "research study detail — per-tab study slice baked into __NEXT_DATA__",
    maxBytes: STUDY_DETAIL_HTML_MAX_BYTES,
    minBytes: STUDY_DETAIL_HTML_MIN_BYTES,
    pathPrefix: "research/studies/",
  },
  {
    comment: "list-linked study detail — full study baked into __NEXT_DATA__",
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
 * Builds the expectation for one study detail tab of the given route family
 * and spot-checked study.
 * @param family - Study detail route family to build the expectation for.
 * @param study - Spot-checked study to build the expectation for.
 * @param tab - Study detail tab to build the expectation for.
 * @returns Route expectation for the tab.
 */
function buildStudyDetailExpectation(
  family: StudyDetailFamily,
  study: KnownStudy,
  tab: StudyDetailTab
): RouteExpectation {
  return {
    body: BODY_EXPECTATION.RENDERED,
    comment: `${family.comment} — ${study.id}, ${study.note} (${tab.label})`,
    maxBytes: family.maxBytes,
    minBytes: family.minBytes,
    relPath: `${family.pathPrefix}${study.id}${tab.suffix}`,
  };
}

const ROUTE_EXPECTATIONS: RouteExpectation[] = [
  {
    body: BODY_EXPECTATION.RENDERED,
    comment: "homepage — presentational shell, no baked entity payload",
    maxBytes: SHELL_HTML_MAX_BYTES,
    minBytes: SHELL_HTML_MIN_BYTES,
    relPath: "index.html",
  },
  {
    body: BODY_EXPECTATION.RENDERED,
    comment:
      "studies list — interactive-table SHELL; the list is fetched at runtime " +
      "from the apiPath JSON and must NOT be baked into __NEXT_DATA__ (the " +
      "shell ceiling sits far below the list size to catch that)",
    maxBytes: SHELL_HTML_MAX_BYTES,
    minBytes: SHELL_HTML_MIN_BYTES,
    relPath: "studies.html",
  },
  {
    body: BODY_EXPECTATION.RENDERED,
    comment: "platforms list — platforms list baked into __NEXT_DATA__",
    maxBytes: PLATFORMS_HTML_MAX_BYTES,
    minBytes: PLATFORMS_HTML_MIN_BYTES,
    relPath: "platforms.html",
  },
  ...STUDY_DETAIL_FAMILIES.flatMap((family) =>
    KNOWN_STUDY_IDS.flatMap((study) =>
      STUDY_DETAIL_TABS.map((tab) =>
        buildStudyDetailExpectation(family, study, tab)
      )
    )
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
