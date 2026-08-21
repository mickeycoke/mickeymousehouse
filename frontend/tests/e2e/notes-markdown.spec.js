// Broadcast notes render Markdown, and the note scrolls.
//
// Notes were plain text with `whitespace-pre-wrap`, so a release note pasted in
// showed its `##` and `**` literally. And an unbounded card pushed Disregard and
// Ask a question off the bottom — on a phone the actions became unreachable.
//
// The renderer deliberately emits React elements and NEVER raw HTML, so the last
// test here asserts that a note containing markup is displayed as text rather
// than parsed. Notes are admin-authored, but "the author is trusted" is not a
// security model — an admin can paste something they were sent.
import { test, expect } from '@playwright/test'

const API = 'http://localhost:8000'

const MD = `# What's new

## Sessions
- **Duo has tabs** now
- Notes are *read-only* until you tap Edit

Some prose with a [link](https://example.com) and \`inline code\`.

| Screen | Change |
|---|---|
| Routines | search |
| Duo | three views |

> Stepping away no longer stops your timer.
`

async function token(request) {
  const res = await request.post(`${API}/api/auth/login`, {
    data: { email: 'admin@example.com', password: 'admin123' },
  })
  return (await res.json()).access_token
}

async function login(page) {
  await page.goto('/login')
  await page.fill('[data-testid="login-email-input"]', 'admin@example.com')
  await page.fill('[data-testid="login-password-input"]', 'admin123')
  await page.click('[data-testid="login-submit-button"]')
  await expect(page).not.toHaveURL(/\/login/, { timeout: 30_000 })
}

async function postNote(request, tok, body) {
  const res = await request.post(`${API}/api/admin/notes`, {
    headers: { Authorization: `Bearer ${tok}` },
    data: { body, is_active: true, attachment_ids: [] },
  })
  if (!res.ok()) throw new Error(`note create failed: ${res.status()} ${await res.text()}`)
  return res.json()
}

async function cleanup(request, tok, id) {
  await request.delete(`${API}/api/admin/notes/${id}`, {
    headers: { Authorization: `Bearer ${tok}` },
  }).catch(() => {})
}

test.describe('Broadcast notes: markdown + scrollable', () => {
  test('a markdown note renders as formatted elements, not literal syntax', async ({ page, request }) => {
    const tok = await token(request)
    const note = await postNote(request, tok, MD)
    try {
      await login(page)
      await page.goto('/notes')
      const body = page.locator('[data-testid="note-body"]').first()
      await expect(body).toBeVisible({ timeout: 30_000 })

      // Real elements, not text that happens to contain the markers.
      await expect(body.locator('h2')).toContainText("What's new")
      await expect(body.locator('h3').first()).toContainText('Sessions')
      await expect(body.locator('ul li').first()).toContainText('Duo has tabs')
      await expect(body.locator('strong').first()).toContainText('Duo has tabs')
      await expect(body.locator('em').first()).toContainText('read-only')
      await expect(body.locator('code').first()).toContainText('inline code')
      await expect(body.locator('table th').first()).toContainText('Screen')
      await expect(body.locator('table td').first()).toContainText('Routines')
      await expect(body.locator('blockquote')).toContainText('no longer stops')
      await expect(body.locator('a[href="https://example.com"]')).toHaveText('link')

      // And the raw syntax is NOT on screen.
      const text = await body.innerText()
      expect(text).not.toContain('##')
      expect(text).not.toContain('**Duo has tabs**')
    } finally {
      await cleanup(request, tok, note.id)
    }
  })

  test('the note body is capped and scrolls, so the actions stay reachable', async ({ page, request }) => {
    const tok = await token(request)
    // Long enough to overflow any sane cap.
    const long = `# Long note\n\n${Array.from({ length: 120 }, (_, i) => `- item ${i}`).join('\n')}`
    const note = await postNote(request, tok, long)
    try {
      await login(page)
      await page.goto('/notes')
      const body = page.locator('[data-testid="note-body"]').first()
      await expect(body).toBeVisible({ timeout: 30_000 })

      const { clientH, scrollH, overflowY } = await body.evaluate((el) => ({
        clientH: el.clientHeight,
        scrollH: el.scrollHeight,
        overflowY: getComputedStyle(el).overflowY,
      }))
      expect(overflowY, 'note body must scroll its own overflow').toMatch(/auto|scroll/)
      expect(scrollH, 'a 120-item note should exceed the capped height').toBeGreaterThan(clientH)

      // The point of the cap: the buttons are still on screen.
      await expect(page.locator('[data-testid="note-disregard"]').first()).toBeInViewport()
    } finally {
      await cleanup(request, tok, note.id)
    }
  })

  test('markup inside a note is shown as text, never parsed', async ({ page, request }) => {
    const tok = await token(request)
    const nasty = 'Heads up: <img src=x onerror="window.__pwned=1"> and <b>not bold</b>'
    const note = await postNote(request, tok, nasty)
    try {
      await login(page)
      await page.goto('/notes')
      const body = page.locator('[data-testid="note-body"]').first()
      await expect(body).toBeVisible({ timeout: 30_000 })

      await expect(body.locator('img')).toHaveCount(0)
      await expect(body.locator('b')).toHaveCount(0)
      await expect(body).toContainText('<b>not bold</b>')
      expect(await page.evaluate(() => window.__pwned)).toBeUndefined()
    } finally {
      await cleanup(request, tok, note.id)
    }
  })

  test('the admin composer previews the rendered markdown before posting', async ({ page }) => {
    await login(page)
    await page.goto('/notes')
    const input = page.locator('[data-testid="admin-note-input"]')
    await expect(input).toBeVisible({ timeout: 30_000 })
    await input.fill('## Draft heading\n\n- one\n- two')

    const preview = page.locator('[data-testid="admin-note-preview"]')
    await expect(preview).toBeVisible()
    await expect(preview.locator('h3')).toContainText('Draft heading')
    await expect(preview.locator('ul li')).toHaveCount(2)
  })
})
