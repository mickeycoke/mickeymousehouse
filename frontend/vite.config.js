import { execSync } from 'node:child_process'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import legacy from '@vitejs/plugin-legacy'

// WHICH CHECKOUT IS THIS, AND AT WHAT COMMIT?
//
// A port number alone can't tell you what it's serving when more than one
// dev server or worktree is running, so the build stamps the branch/commit
// into index.html. The same meta tag drives both the on-screen dev badge and
// any E2E guard that wants to refuse running against a stale bundle.
function gitInfo() {
  const run = (cmd) => {
    try {
      return execSync(cmd, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()
    } catch {
      return ''
    }
  }
  return {
    branch: run('git rev-parse --abbrev-ref HEAD') || 'unknown',
    sha: run('git rev-parse --short HEAD') || 'unknown',
    // The checkout path is what distinguishes two worktrees on the same branch.
    checkout: run('git rev-parse --show-toplevel') || process.cwd(),
    dirty: run('git status --porcelain') !== '',
  }
}

// Computed PER REQUEST in dev, not once at boot.
//
// `transformIndexHtml` runs on every index.html request, and a dev server serves
// live source over HMR — so the code really is current even when the process is
// hours old. Stamping at boot made the sha go stale the moment anything was
// committed, and the E2E guard would then abort every run until someone
// restarted the server. A guard that cries wolf after every commit is a guard
// people learn to skip.
//
// A 2s cache keeps this from spawning git repeatedly; index.html is requested
// rarely enough that it barely matters, and 2s is short enough that the stamp is
// never meaningfully behind.
let cached = { at: 0, value: null }
function currentStamp() {
  const now = Date.now()
  if (cached.value && now - cached.at < 2000) return cached.value
  const info = gitInfo()
  cached = {
    at: now,
    value: { ...info, stamp: `${info.branch}@${info.sha}${info.dirty ? '+dirty' : ''}` },
  }
  return cached.value
}

export default defineConfig({
  plugins: [
    react(),
    // Owner report 2026-08-16: old front-desk iPads failing to enter the
    // session screen. Emits a second, transpiled + polyfilled bundle that
    // browsers below the modern floor load instead (Safari/iOS 11+, and any
    // ES2015-capable engine); modern browsers ignore it entirely, so their
    // bundle and behavior are unchanged. `renderModernChunks` stays true so
    // the primary bundle keeps the es2020 build.target below.
    //
    // THE SUPPORT FLOOR LIVES HERE (a product decision, not a toolchain
    // default): plugin-legacy owns build.target, so a plain `build.target`
    // is overridden and would silently disagree with this. Modern bundle =
    // Vite's es2020 baseline (Safari 14 / Chrome 87 / Firefox 78 / Edge 88,
    // the "best experience" tier); legacy bundle = the targets below (the
    // "still supported" tier). Documented for users in HelpPage.jsx
    // ("System requirements") — change both together.
    legacy({
      targets: ['defaults', 'iOS >= 11', 'Safari >= 11', 'not IE 11'],
      modernPolyfills: false,
    }),
    {
      // A meta tag rather than only a JS global: the E2E guard and a plain
      // `curl` can both read it without executing the app.
      name: 'pt-dev-stamp',
      transformIndexHtml(html) {
        const info = currentStamp()
        return html.replace(
          '</head>',
          `  <meta name="pt-dev-build" content="${info.stamp}">\n` +
          `  <meta name="pt-dev-checkout" content="${info.checkout}">\n</head>`,
        )
      },
    },
  ],
  server: {
    port: 5173,
    // Fail loudly instead of silently hopping to the next free port, so a
    // busy 5173 is obvious rather than producing a second server nobody
    // meant to start.
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
