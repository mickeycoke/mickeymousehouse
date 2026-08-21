// Stripe Studio Billing — the platform's OWN revenue: a
// studio pays a recurring monthly subscription. Separate from Client
// Payments (client-payments.spec.js).
//
// The feature ships DORMANT: it's gated on a platform-wide config
// (BILLING_ENABLED + Stripe keys) exposed at GET /api/admin/billing/config.
// In dev and CI those keys are unset, so config.enabled is false and the
// admin billing screen must show only the "not configured" message — no
// studio table, no fetch of the roster. This spec locks that default-off
// state in. We deliberately do NOT drive a live Stripe Checkout (no keys, no
// network); the checkout/webhook flow belongs in the backend suite with
// stripe mocked.
import { test, expect } from './fixtures.js'

const API = 'http://localhost:8000'

async function login(page) {
  await page.goto('/login')
  await page.fill('[data-testid="login-email-input"]', 'admin@example.com')
  await page.fill('[data-testid="login-password-input"]', 'admin123')
  await page.click('[data-testid="login-submit-button"]')
  await expect(page).toHaveURL(/\/admin\/overview/, { timeout: 30000 })
}

test.describe('Studio billing — feature disabled by default', () => {
  test('config reports disabled and the admin billing screen shows no studio table', async ({ page, request }) => {
    // With no Stripe billing keys configured, the public gate must report off.
    const cfg = await (await request.get(`${API}/api/admin/billing/config`)).json()
    expect(cfg.enabled).toBe(false)

    await login(page)

    await page.goto('/setup/billing')
    await expect(page.locator('[data-testid="billing-page"]')).toBeVisible()
    await expect(page.locator('[data-testid="billing-disabled-message"]')).toBeVisible()

    // Nothing new renders while disabled — no roster, no per-row controls.
    await expect(page.locator('[data-testid="billing-studio-row"]')).toHaveCount(0)
    await expect(page.locator('[data-testid="billing-amount-input"]')).toHaveCount(0)
    await expect(page.locator('[data-testid="billing-checkout-button"]')).toHaveCount(0)
  })

  test('the Billing card on the Manage dashboard links to /setup/billing', async ({ page }) => {
    await login(page)
    await page.goto('/setup')
    await expect(page.locator('[data-testid="setup-nav-billing"]')).toBeVisible()
    await page.click('[data-testid="setup-nav-billing"]')
    await expect(page).toHaveURL(/\/setup\/billing/)
    await expect(page.locator('[data-testid="billing-disabled-message"]')).toBeVisible()
  })
})
