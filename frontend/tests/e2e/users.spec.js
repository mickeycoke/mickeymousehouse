// Admin user CRUD tests.
// Creates a uniquely-named user per run, edits it, then deletes it, so the
// suite can run repeatedly against the same seeded database.
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

async function gotoUsersPage(page) {
  await page.click('[data-testid="sidebar-nav-users"]')
  await expect(page).toHaveURL('/admin/users')
  await expect(page.locator('[data-testid="users-table"]')).toBeVisible()
}

test.describe('Admin user management', () => {
  test('users table lists the seeded admin', async ({ page }) => {
    await loginAsAdmin(page)
    await gotoUsersPage(page)
    await expect(page.locator('[data-testid="users-table"]')).toContainText('admin@example.com')
  })

  test('create, edit, and delete a user through the UI', async ({ page }) => {
    const stamp = Date.now()
    const name = `E2E User ${stamp}`
    const email = `e2e-user-${stamp}@example.com`
    const renamed = `E2E Renamed ${stamp}`

    await loginAsAdmin(page)
    await gotoUsersPage(page)

    // Create
    await page.click('[data-testid="users-add-button"]')
    await page.fill('[data-testid="user-form-name-input"]', name)
    await page.fill('[data-testid="user-form-email-input"]', email)
    await page.fill('[data-testid="user-form-password-input"]', 'password123')
    await page.selectOption('[data-testid="user-form-role-select"]', 'instructor')
    await page.click('[data-testid="user-form-submit-button"]')
    await expect(page.locator('[data-testid="users-table"]')).toContainText(email)

    const row = page.locator('[data-testid="users-table"] tr', { hasText: email })

    // Edit
    await row.locator('[data-testid="users-edit-button"]').click()
    await page.fill('[data-testid="user-form-name-input"]', renamed)
    await page.selectOption('[data-testid="user-form-role-select"]', 'manager')
    await page.click('[data-testid="user-form-submit-button"]')
    await expect(page.locator('[data-testid="users-table"]')).toContainText(renamed)
    await expect(row).toContainText('manager')

    // Delete (deactivates the account and removes it from the table)
    await row.locator('[data-testid="users-delete-button"]').click()
    await page.click('[data-testid="delete-confirm-button"]')
    await expect(page.locator('[data-testid="users-table"]')).not.toContainText(email)
  })

  test('add-user form can be cancelled without changes', async ({ page }) => {
    await loginAsAdmin(page)
    await gotoUsersPage(page)
    await page.click('[data-testid="users-add-button"]')
    await expect(page.locator('[data-testid="user-form-name-input"]')).toBeVisible()
    await page.click('[data-testid="user-form-cancel-button"]')
    await expect(page.locator('[data-testid="user-form-name-input"]')).not.toBeVisible()
  })
})
