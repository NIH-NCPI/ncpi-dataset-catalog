import { defineConfig } from "@playwright/test";

export default defineConfig({
  fullyParallel: false,
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  reporter: [["list"], ["html", { open: "never" }]],
  retries: 1,
  testDir: "e2e",
  timeout: 90_000,
  use: {
    baseURL: "http://localhost:3000",
  },
  webServer: [
    {
      command: "make -C backend start",
      port: 8000,
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command:
        "./scripts/dev.sh ncpi-catalog dev && ./scripts/set-version.sh dev && ./scripts/sync-api.sh && next dev",
      env: { NEXT_PUBLIC_SEARCH_API_URL: "http://localhost:8000/search" },
      port: 3000,
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
  workers: 1,
});
