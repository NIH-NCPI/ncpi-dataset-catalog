import { defineConfig } from "@playwright/test";

// Searches go to the deployed dev API from .env.development by default.
// Set E2E_LOCAL_BACKEND=true to start the local backend on :8000 and serve
// the app with `npm run dev:local`, which points search at it (the backend
// needs ANTHROPIC_API_KEY to parse queries).
const useLocalBackend = process.env.E2E_LOCAL_BACKEND === "true";

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
    ...(useLocalBackend
      ? [
          {
            command: "make -C backend start",
            port: 8000,
            reuseExistingServer: true,
            timeout: 30_000,
          },
        ]
      : []),
    {
      command: useLocalBackend ? "npm run dev:local" : "npm run dev",
      port: 3000,
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
  workers: 1,
});
