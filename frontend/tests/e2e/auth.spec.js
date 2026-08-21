// Login/logout flow tests.
// Relies on the seeded admin account (admin@example.com / admin123).
import { test, expect } from './fixtures.js'

async function loginAsAdmin(page) {
  await page.goto('/login')
  await page.fill('[data-testid="login-email-input"]', 'admin@example.com')
  await page.fill('[data-testid="login-password-input"]', 'admin123')
  await page.click('[data-testid="login-submit-button"]')
  // bcrypt plus a production-scale local database: the login round-trip is
  // ~0.2s idle but seconds while the suite hammers the backend. The
  // assertion is unchanged - only the patience for it is.
  await expect(page).toHaveURL('/admin/overview', { timeout: 20000 })
}

test.describe('Authentication', () => {
  test('valid credentials log in and land on the hub dashboard', async ({ page }) => {
    await loginAsAdmin(page)
    await expect(page.locator('[data-testid="sidebar-logout-button"]')).toBeVisible()
  })

  test('malformed email shows a friendly error, not a crash', async ({ page }) => {
    // Regression: FastAPI 422 validation errors are arrays of objects —
    // rendering them raw crashed the whole app (white "failed to load" page).
    await page.goto('/login')
    await page.fill('[data-testid="login-email-input"]', 'not-an-email')
    await page.fill('[data-testid="login-password-input"]', 'whatever')
    await page.click('[data-testid="login-submit-button"]')
    await expect(page.locator('[data-testid="login-error-message"]')).toBeVisible()
    // The app must still be alive and usable
    await expect(page.locator('[data-testid="login-submit-button"]')).toBeEnabled()
  })

  test('wrong password shows an error and stays on login', async ({ page }) => {
    await page.goto('/login')
    await page.fill('[data-testid="login-email-input"]', 'admin@example.com')
    await page.fill('[data-testid="login-password-input"]', 'wrong-password')
    await page.click('[data-testid="login-submit-button"]')
    await expect(page.locator('[data-testid="login-error-message"]')).toBeVisible()
    await expect(page).toHaveURL('/login')
  })

  test('unknown email shows an error and stays on login', async ({ page }) => {
    await page.goto('/login')
    await page.fill('[data-testid="login-email-input"]', 'nobody@example.com')
    await page.fill('[data-testid="login-password-input"]', 'admin123')
    await page.click('[data-testid="login-submit-button"]')
    await expect(page.locator('[data-testid="login-error-message"]')).toBeVisible()
    await expect(page).toHaveURL('/login')
  })

  test('logout returns to login and protected pages redirect again', async ({ page }) => {
    await loginAsAdmin(page)
    await page.click('[data-testid="sidebar-logout-button"]')
    await expect(page).toHaveURL('/login')

    await page.goto('/admin/overview')
    await expect(page).toHaveURL('/login')
  })

  test('session survives a page refresh', async ({ page }) => {
    await loginAsAdmin(page)
    await page.reload()
    await expect(page).toHaveURL('/admin/overview')
    await expect(page.locator('[data-testid="sidebar-logout-button"]')).toBeVisible()
  })
})
