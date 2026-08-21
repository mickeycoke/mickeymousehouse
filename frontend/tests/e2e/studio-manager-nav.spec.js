import { test, expect } from './fixtures.js'
import { createTestStudio } from './helpers/studios.js'

// ---------------------------------------------------------------------------
// Studio Manager nav tab
//
// The "Studio Manager" sidebar item is a discoverable entry point to the
// instructor-onboarding / shared front-desk device links that previously
// lived only inside Profile (ProfilePage.jsx's `managesStudios` card, which
// is untouched — this is an ADDITIONAL entry point, not a replacement).
// Gate under test (Sidebar.jsx `studioManagerTab` branch — mirrors
// ProfilePage.jsx's `managesStudios`):
//   (myRoles?.studio_owner || myRoles?.studio_manager) && user?.role !== 'admin'
// So: a studio manager/owner login sees it, an admin login does not (admins
// use the Studios page instead).
// ---------------------------------------------------------------------------

async function loginAdmin(page) {
  await page.goto('/login')
  await page.fill('[data-testid="login-email-input"]', 'admin@example.com')
  await page.fill('[data-testid="login-password-input"]', 'admin123')
  await page.click('[data-testid="login-submit-button"]')
  // bcrypt plus a production-scale local database: the login round-trip is
  // ~0.2s idle but seconds while the suite hammers the backend. The
  // assertion is unchanged - only the patience for it is.
  await expect(page).toHaveURL(/\/admin\/overview/, { timeout: 20000 })
}

async function adminHeaders(request) {
  const res = await request.post('http://localhost:8000/api/auth/login', {
    data: { email: 'admin@example.com', password: 'admin123' },
  })
  const { access_token } = await res.json()
  return { Authorization: `Bearer ${access_token}` }
}

// Creates a disposable studio + a fresh 'manager' user assigned as that
// studio's owner (StudioOwner.level='owner' -> myRoles.studio_owner=true),
// mirroring how ownership.spec.js (makeFranchiseAndOwnerCandidate) builds
// throwaway fixtures rather than reusing shared seed users.
async function makeStudioManagerLogin(request, label) {
  const headers = await adminHeaders(request)
  const stamp = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
  const email = `e2e-studio-mgr-${label}-${stamp}@example.com`
  const password = 'password123'

  const studio = await createTestStudio(request, `studio-mgr-${label}`, headers)

  const userRes = await request.post('http://localhost:8000/api/users', {
    headers,
    data: { name: `E2E Studio Manager ${label} ${stamp}`, email, password, role: 'manager' },
  })
  const user = await userRes.json()
  expect(user.id, `user create failed: ${JSON.stringify(user)}`).toBeTruthy()

  const assignRes = await request.post('http://localhost:8000/api/studio-owners', {
    headers,
    data: { user_id: user.id, studio_id: studio.id, level: 'owner' },
  })
  expect(assignRes.ok(), `studio-owner assign failed: ${assignRes.status()} ${await assignRes.text()}`).toBeTruthy()

  return { email, password, studio }
}

async function loginAs(page, email, password) {
  await page.goto('/login')
  await page.fill('[data-testid="login-email-input"]', email)
  await page.fill('[data-testid="login-password-input"]', password)
  await page.click('[data-testid="login-submit-button"]')
  await expect(page).toHaveURL(/\/admin\/overview/, { timeout: 20000 })
}

test.describe('Studio Manager nav tab', () => {
  test('studio owner/manager login sees the Studio Manager nav item, admin does not', async ({ page, request }) => {
    const { email, password } = await makeStudioManagerLogin(request, 'visibility')

    await loginAs(page, email, password)
    await expect(page.locator('[data-testid="sidebar-nav-studio-manager"]')).toBeVisible()

    await page.evaluate(() => {
      localStorage.removeItem('access_token')
      localStorage.removeItem('auth_user')
    })
    await loginAdmin(page)
    await expect(page.locator('[data-testid="sidebar-nav-studio-manager"]')).toHaveCount(0)
  })

  test('clicking through shows the studio onboarding and shared-device codes', async ({ page, request }) => {
    const { email, password, studio } = await makeStudioManagerLogin(request, 'codes')

    await loginAs(page, email, password)
    await page.click('[data-testid="sidebar-nav-studio-manager"]')
    await expect(page).toHaveURL('/studio-manager')
    await expect(page.locator('[data-testid="studio-manager-page"]')).toBeVisible()
    await expect(page.locator('[data-testid="studio-manager-page"]')).toContainText(studio.display_name || studio.name)

    await page.locator('[data-testid="studio-manager-codes-button"]').first().click()
    await expect(page.locator('[data-testid="studio-codes-modal"]')).toBeVisible()
    await expect(page.locator('[data-testid="studio-codes-onboard"]')).toBeVisible()
    await expect(page.locator('[data-testid="studio-codes-shared"]')).toBeVisible()
  })
})
