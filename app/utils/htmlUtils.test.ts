import { stripHtmlTags } from "./htmlUtils";

describe("stripHtmlTags", () => {
  it("removes HTML tags from a string", () => {
    expect(stripHtmlTags("<p>Hello <b>world</b></p>")).toBe("Hello world");
  });

  it("handles self-closing tags", () => {
    expect(stripHtmlTags("line one<br/>line two")).toBe("line oneline two");
  });

  it("collapses whitespace", () => {
    expect(stripHtmlTags("<p>  multiple   spaces  </p>")).toBe(
      "multiple spaces"
    );
  });

  it("returns empty string for empty input", () => {
    expect(stripHtmlTags("")).toBe("");
  });

  it("returns plain text unchanged", () => {
    expect(stripHtmlTags("no tags here")).toBe("no tags here");
  });

  it("handles nested tags", () => {
    expect(stripHtmlTags("<div><p>Nested <em>content</em></p></div>")).toBe(
      "Nested content"
    );
  });
});
