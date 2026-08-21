// "Copy setup link" — reset someone's password with no email involved.
//
// If the mail host began rejecting the app's credential, that would take out
// password reset AND the setup email at once, leaving no way to get anyone
// back into an account without a server shell. This path does not touch the
// email service at all.
//
// The two things worth pinning in a browser rather than only in pytest:
//   1. the link is VISIBLE, not merely copied — clipboard access needs a secure
//      context and can be denied, and a link you cannot see is no use at the
//      front desk;
//   2. the whole round trip works from the admin's screen to a working sign-in.
//
// AUTHORIZATION IS NOT TESTED HERE, deliberately — it lives in
// backend/tests/test_setup_link.py, which asserts the invariant that this
// endpoint never grants more than PUT /api/users/{id}. An earlier version of
// this file implied it covered authorization while running only as admin, which
// is exactly the false-confidence shape a QA review would call out.
import { test, expect } from './fixtures.js'

const API = 'http://localhost:8000'

async function adminHeaders(request) {
  const res = await request.post(`${API}/api/auth/login`, {
    data: { email: 'admin@example.com', password: 'admin123' },
  })
  expect(res.ok(), 'admin login must succeed').toBeTruthy()
  return { Authorization: `Bearer ${(await res.json()).access_token}` }
}

test.describe('Setup link hand-over (no email)', () => {
  test('an admin issues a link and the user signs in with a password they chose', async ({ page, request }) => {
    const stamp = Date.now()
    const email = `handover-${stamp}@example.com`
    const headers = await adminHeaders(request)

    // A user with NO password set — the shape of an imported
    // staff record that still needs one.
    const created = await request.post(`${API}/api/users`, {
      headers,
      data: { name: `Hand Over ${stamp}`, email, role: 'instructor' },
    })
    expect(created.ok(), `seeding the user failed: ${created.status()}`).toBeTruthy()
    const user = await created.json()

    // Log in through the UI so the app's own storage keys are used, rather
    // than hand-writing them (the previous version guessed the key name wrong
    // and every seeded request ran unauthenticated).
    await page.goto('/login')
    await page.fill('[data-testid="login-email-input"]', 'admin@example.com')
    await page.fill('[data-testid="login-password-input"]', 'admin123')
    await page.click('[data-testid="login-submit-button"]')
    await expect(page).toHaveURL('/admin/overview', { timeout: 20000 })

    await page.goto('/admin/users')
    await expect(page.locator('[data-testid="users-table"]')).toBeVisible({ timeout: 20000 })

    // Filter to exactly this user, so the button we press is unambiguously
    // theirs. NO try/catch here: if the search breaks, this test must fail
    // rather than quietly act on whoever happens to be in row one.
    await page.fill('[data-testid="users-search-input"]', email)
    const buttons = page.locator('[data-testid="users-setup-link-button"]')
    await expect(buttons).toHaveCount(1, { timeout: 15000 })
    await buttons.click()

    const linkBox = page.locator('[data-testid="users-setup-link-value"]')
    await expect(linkBox).toBeVisible({ timeout: 15000 })
    const link = await linkBox.inputValue()
    expect(link).toContain('/set-password?token=')
    // A link with no stated life gets pinned to a noticeboard.
    await expect(page.locator('[data-testid="users-invite-notice"]')).toContainText('72 hours')

    // Now be the recipient: drop the admin session, open the link, choose a
    // password.
    const chosen = `Chosen-${stamp}!`
    await page.evaluate(() => localStorage.clear())
    const url = new URL(link)
    await page.goto(url.pathname + url.search)

    await page.fill('[data-testid="set-password-input"]', chosen)
    await page.fill('[data-testid="set-password-confirm-input"]', chosen)
    await page.click('[data-testid="set-password-submit-button"]')
    await expect(page).not.toHaveURL(/set-password/, { timeout: 20000 })

    // The real proof: a cold login with the password they picked.
    const login = await request.post(`${API}/api/auth/login`, {
      data: { email, password: chosen },
    })
    expect(login.status()).toBe(200)

    await request.delete(`${API}/api/users/${user.id}`, { headers })
  })

  test('a user with no email is refused, with a reason that points at the PIN', async ({ request }) => {
    const stamp = Date.now()
    const headers = await adminHeaders(request)

    const created = await request.post(`${API}/api/users`, {
      headers,
      data: { name: `Pin Only ${stamp}`, role: 'instructor' },
    })
    expect(created.ok(), `seeding the user failed: ${created.status()}`).toBeTruthy()
    const user = await created.json()

    const res = await request.post(`${API}/api/auth/setup-link`, {
      headers,
      data: { user_id: user.id },
    })
    expect(res.status()).toBe(400)
    const detail = (await res.json()).detail.toLowerCase()
    expect(detail).toContain('no email')
    expect(detail).toContain('pin')

    await request.delete(`${API}/api/users/${user.id}`, { headers })
  })
})
