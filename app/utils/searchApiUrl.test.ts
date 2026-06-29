import { getSearchApiUrl } from "./searchApiUrl";

describe("getSearchApiUrl", () => {
  const ORIGINAL_ENV = process.env.NEXT_PUBLIC_SEARCH_API_URL;

  afterEach(() => {
    if (ORIGINAL_ENV === undefined) {
      delete process.env.NEXT_PUBLIC_SEARCH_API_URL;
    } else {
      process.env.NEXT_PUBLIC_SEARCH_API_URL = ORIGINAL_ENV;
    }
  });

  it("returns the config URL when the env var is unset", () => {
    delete process.env.NEXT_PUBLIC_SEARCH_API_URL;
    expect(getSearchApiUrl("https://api.example.com/search")).toBe(
      "https://api.example.com/search"
    );
  });

  it("prefers the env var over the config URL", () => {
    process.env.NEXT_PUBLIC_SEARCH_API_URL = "https://env.example.com/search";
    expect(getSearchApiUrl("https://config.example.com/search")).toBe(
      "https://env.example.com/search"
    );
  });

  it("returns an empty string when neither is set", () => {
    delete process.env.NEXT_PUBLIC_SEARCH_API_URL;
    expect(getSearchApiUrl()).toBe("");
  });

  it("appends /agent when agent mode is requested", () => {
    delete process.env.NEXT_PUBLIC_SEARCH_API_URL;
    expect(
      getSearchApiUrl("https://api.example.com/search", { agent: true })
    ).toBe("https://api.example.com/search/agent");
  });

  it("returns an empty string for agent mode when no base URL is set", () => {
    delete process.env.NEXT_PUBLIC_SEARCH_API_URL;
    expect(getSearchApiUrl(undefined, { agent: true })).toBe("");
  });
});
