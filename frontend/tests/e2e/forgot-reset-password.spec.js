// Self-service password reset: no-enumeration on the forgot-password page,
// and the full request -> reset -> logged-in happy path.
//
// TOKEN-RETRIEVAL NOTE — read this before changing the happy-path test:
// There is no existing frontend e2e spec for the invite/set-password flow to
// mirror a link-retrieval mechanism from (checked frontend/tests/e2e/ — the
// only invite/set-password coverage lives in backend/tests/test_invite_flow.py,
// which reads InviteResponse.invite_link because /api/auth/invite is an
// AUTHENTICATED admin endpoint that deliberately echoes the dev link back).
// /api/auth/forgot-password has no equivalent field, on purpose: it is public
// and unauthenticated, and ForgotPasswordResponse must be byte-for-byte
// identical whether or not the email matched a user (see the comment on that
// schema) — so there is no enumeration-safe way to surface the token over
// HTTP, even in dev.
//
// So the happy-path test mints its own token the same way the backend's own
// test fixtures do: by calling the real create_reset_token() (backend/app/
// utils/tokens.py) for a throwaway user, via `docker compose exec`. This
// never touches or weakens the public forgot-password response — it only
// substitutes for the email-delivery step, which Playwright has no way to
// observe. The request step above it still goes through the real UI and the
// real endpoint, so that contract stays covered.
import { execSync } from 'node:child_process'
import { test, expect } from './fixtures.js'

const ADMIN_EMAIL = 'admin@example.com'
const ADMIN_PASSWORD = 'admin123'

async function adminHeaders(request) {
  const res = await request.post('http://localhost:8000/api/auth/login', {
    data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
  })
  const { access_token } = await res.json()
  return { Authorization: `Bearer ${access_token}` }
}

function mintResetToken(userId) {
  return execSync(
    `docker compose exec -T backend python -c "from app.utils.tokens import create_reset_token; print(create_reset_token('${userId}'))"`,
    { cwd: '..', encoding: 'utf8' },
  ).trim()
}

test.describe('Forgot / reset password', () => {
  test('an unknown email gets the same generic message as a known one', async ({ page }) => {
    await page.goto('/forgot-password')
    await page.fill('[data-testid="forgot-password-email-input"]', ADMIN_EMAIL)
    await page.click('[data-testid="forgot-password-submit-button"]')
    const knownMessage = await page
      .locator('[data-testid="forgot-password-success-message"]')
      .innerText()

    await page.goto('/forgot-password')
    await page.fill(
      '[data-testid="forgot-password-email-input"]',
      `no-such-user-${Date.now()}@example.com`,
    )
    await page.click('[data-testid="forgot-password-submit-button"]')
    const unknownMessage = await page
      .locator('[data-testid="forgot-password-success-message"]')
      .innerText()

    expect(knownMessage).toBe(unknownMessage)
    expect(knownMessage).toContain('If an account exists for that email')
  })

  test('request -> reset -> lands logged in', async ({ page, request }) => {
    const stamp = Date.now()
    const email = `e2e-forgot-pw-${stamp}@example.com`
    const name = `E2E ForgotPW ${stamp}`
    const headers = await adminHeaders(request)

    const createRes = await request.post('http://localhost:8000/api/users', {
      headers,
      data: { name, email, password: 'original-pw-123', role: 'instructor' },
    })
    expect(createRes.ok()).toBeTruthy()
    const user = await createRes.json()

    try {
      // Real UI, real endpoint — this is the part the enumeration test above
      // also exercises. We only skip watching the outbound email.
      await page.goto('/forgot-password')
      await page.fill('[data-testid="forgot-password-email-input"]', email)
      await page.click('[data-testid="forgot-password-submit-button"]')
      await expect(
        page.locator('[data-testid="forgot-password-success-message"]'),
      ).toBeVisible()

      const token = mintResetToken(user.id)

      await page.goto(`/reset-password?token=${token}`)
      await expect(page.locator('[data-testid="reset-password-input"]')).toBeVisible()
      await page.fill('[data-testid="reset-password-input"]', 'brand-new-pw-456')
      await page.fill('[data-testid="reset-password-confirm-input"]', 'brand-new-pw-456')
      await page.click('[data-testid="reset-password-submit-button"]')

      await expect(page).toHaveURL('/admin/overview', { timeout: 20000 })
    } finally {
      await request.delete(`http://localhost:8000/api/users/${user.id}`, { headers })
    }
  })

  test('an invalid token shows the generic invalid-link message', async ({ page }) => {
    await page.goto('/reset-password?token=not-a-real-token')
    await expect(page.locator('[data-testid="reset-password-invalid-message"]')).toBeVisible()
  })
})
