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

test.describe('Navigation and deep links', () => {
  test('root URL redirects unauthenticated users to login', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL('/login')
  })

  test('/admin redirects authenticated users to overview', async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/admin')
    await expect(page).toHaveURL('/admin/overview')
  })

  test('sidebar links navigate between admin sections', async ({ page }) => {
    await loginAsAdmin(page)
    await page.click('[data-testid="sidebar-nav-users"]')
    await expect(page).toHaveURL('/admin/users')
    await expect(page.locator('[data-testid="users-table"]')).toBeVisible()

    await page.click('[data-testid="sidebar-nav-overview"]')
    await expect(page).toHaveURL('/admin/overview')
    // Admin with no studio selected: the per-studio board asks them to pick one.
    await expect(page.locator('[data-testid="dashboard-select-studio"]')).toBeVisible()
  })

  test('deep link returns to requested page after login', async ({ page }) => {
    await page.goto('/admin/users')
    await expect(page).toHaveURL('/login')

    await page.fill('[data-testid="login-email-input"]', 'admin@example.com')
    await page.fill('[data-testid="login-password-input"]', 'admin123')
    await page.click('[data-testid="login-submit-button"]')

    await expect(page).toHaveURL('/admin/users')
    await expect(page.locator('[data-testid="users-table"]')).toBeVisible()
  })

  test('admin dashboard requires a studio before showing the board', async ({ page }) => {
    await loginAsAdmin(page)
    // The on-deck board is per-studio, so an admin must choose a studio first
    // rather than seeing a franchise-wide mashup.
    await expect(page.locator('[data-testid="dashboard-select-studio"]')).toBeVisible()
    await expect(page.locator('[data-testid="dashboard-choose-studio"]')).toBeVisible()
  })
})
