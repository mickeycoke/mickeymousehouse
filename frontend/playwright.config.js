import { defineConfig } from '@playwright/test'

// E2E_PORT lets a second checkout (e.g. a worktree) run the suite on its own
// dev-server port while the usual one stays on 5173.
const port = Number(process.env.E2E_PORT || 5173)

export default defineConfig({
  testDir: './tests/e2e',
  // Refuses to run against a remote/production backend — see global-setup.js.
  globalSetup: './tests/e2e/global-setup.js',
  // Retires the studios the specs create. Without it dev accumulated 84 active
  // test studios against 17 real ones.
  globalTeardown: './tests/e2e/global-teardown.js',
  // The local database is production-scale (~14M metric values), so a request
  // that takes ~0.2s idle can take seconds while the serial suite hammers the
  // backend continuously. With the 5s default, whichever test happened to run
  // during a slow patch failed — a different one each run, always passing in
  // isolation. These are patience, not tolerance: every assertion is unchanged
  // and a genuinely broken expectation still fails, just later.
  timeout: 60000,
  expect: { timeout: 15000 },
  // All specs share one seeded admin user, and "active session" is global
  // per-instructor state — parallel workers cancel/complete each other's
  // sessions and cause flaky failures. Keep this at 1.
  workers: 1,
  use: {
    baseURL: `http://localhost:${port}`,
    headless: true,
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: 'cd .. && docker compose up -d db backend',
      port: 8000,
      reuseExistingServer: true,
      timeout: 60000,
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`,
      port,
      reuseExistingServer: true,
      timeout: 30000,
    },
  ],
})
