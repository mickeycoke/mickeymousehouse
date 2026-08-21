import { test as base, expect } from '@playwright/test'

// Suppress the login-notes broadcast for every spec except the one that tests it.
//
// WHY THIS EXISTS — it cost a full suite run to find, so it is worth the words.
//
// `LoginNotesModal` (src/components/notes/LoginNotesModal.jsx) shows the admin's
// active notes once per signed-in identity, and remembers that in sessionStorage.
// Playwright gives every test a FRESH browser context, so sessionStorage is
// always empty and the modal re-opens on every single test the moment any note
// is active. Its backdrop is `fixed inset-0 z-50` over `bg-black/40`, which
// intercepts pointer events across the whole app.
//
// Exactly one active note — a "What's new" release broadcast — once
// failed **44 tests** in specs that have nothing to do with notes (auth, setup,
// users, ownership, reporting, workflow), and stretched the suite from 22
// minutes to an hour: every blocked click retried ~100 times before timing out.
// The failure text is always the same and does NOT name the modal:
//   <div aria-hidden="true" class="absolute inset-0 bg-black/40"> … intercepts
//   pointer events
//
// It is neutralised at the API, deliberately, rather than by dismissing the note
// in the database. Dismissing is a real user action recorded per user — it would
// hide the owner's own broadcast from them — and it fixes only the note that
// exists today, so the next one would take the suite down all over again.
//
// notes-markdown.spec.js asserts `note-disregard` is in viewport, so it imports
// from '@playwright/test' directly and still sees the real modal.
// The second argument is Playwright's `use`. It is named `runTest` here purely
// so eslint's react-hooks/rules-of-hooks does not mistake a fixture for a React
// hook — it is positional, so the name is ours to choose.
export const test = base.extend({
  page: async ({ page }, runTest) => {
    await page.route('**/api/notes/active*', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    }))
    await runTest(page)
  },
})

export { expect }
