import fs from "fs";
import path from "path";

const OUT_DIR = path.resolve("out");

/**
 * Extracts an OG meta tag value from HTML.
 * @param html - Raw HTML string.
 * @param property - OG property name (e.g. "og:title").
 * @returns Content value or null if not found.
 */
function getOgTag(html: string, property: string): string | null {
  const re = new RegExp(`property="${property}"\\s+content="([^"]*)"`, "i");
  const match = html.match(re);
  return match?.[1] ?? null;
}

/**
 * Extracts a meta tag value by name attribute from HTML.
 * @param html - Raw HTML string.
 * @param name - Meta name (e.g. "twitter:card").
 * @returns Content value or null if not found.
 */
function getMetaByName(html: string, name: string): string | null {
  const re = new RegExp(`name="${name}"\\s+content="([^"]*)"`, "i");
  const match = html.match(re);
  return match?.[1] ?? null;
}

// Skip if no build output (these tests run after `npm run build:dev`).
const hasOutput = fs.existsSync(OUT_DIR);
const describeIfBuilt = hasOutput ? describe : describe.skip;

describeIfBuilt("OG meta tags in static export", () => {
  const readPage = (pagePath: string): string =>
    fs.readFileSync(path.join(OUT_DIR, pagePath), "utf-8");

  it("homepage has site-level OG tags", () => {
    const html = readPage("index.html");
    expect(getOgTag(html, "og:title")).toBe("NCPI Dataset Catalog");
    expect(getOgTag(html, "og:description")).toContain("2,944 studies");
    expect(getOgTag(html, "og:image")).toContain("web-app-manifest-512x512");
    expect(getOgTag(html, "og:site_name")).toBe("NCPI Dataset Catalog");
    expect(getOgTag(html, "og:type")).toBe("website");
    expect(getMetaByName(html, "twitter:card")).toBe("summary");
  });

  it("example queries page has per-page title", () => {
    const html = readPage("example-queries.html");
    expect(getOgTag(html, "og:title")).toBe(
      "Example Queries - NCPI Dataset Catalog"
    );
  });

  it("research page has per-page title", () => {
    const html = readPage("research/studies.html");
    expect(getOgTag(html, "og:title")).toBe("Research - NCPI Dataset Catalog");
  });

  it("study detail page (/studies/) has study name in title", () => {
    const html = readPage("studies/phs000298.html");
    const title = getOgTag(html, "og:title");
    expect(title).toContain("phs000298");
    expect(title).toContain("NCPI Dataset Catalog");
    expect(title).not.toBe("NCPI Dataset Catalog");
  });

  it("study variables page includes 'Variables' in title", () => {
    const html = readPage("studies/phs000298/variables.html");
    const title = getOgTag(html, "og:title");
    expect(title).toContain("Variables");
    expect(title).toContain("phs000298");
  });

  it("study publications page includes 'Selected Publications' in title", () => {
    const html = readPage("studies/phs000298/selected-publications.html");
    const title = getOgTag(html, "og:title");
    expect(title).toContain("Selected Publications");
    expect(title).toContain("phs000298");
  });

  it("research study detail page has study name in title", () => {
    const html = readPage("research/studies/phs000298.html");
    const title = getOgTag(html, "og:title");
    expect(title).toContain("phs000298");
    expect(title).toContain("NCPI Dataset Catalog");
  });

  it("research study variables page includes 'Variables' in title", () => {
    const html = readPage("research/studies/phs000298/variables.html");
    const title = getOgTag(html, "og:title");
    expect(title).toContain("Variables");
    expect(title).toContain("phs000298");
  });

  it("all pages have favicon links in HTML", () => {
    const html = readPage("index.html");
    expect(html).toContain('href="/favicons/favicon.ico"');
    expect(html).toContain('href="/favicons/apple-touch-icon.png"');
  });
});
