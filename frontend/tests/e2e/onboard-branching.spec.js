// After PIN verification succeeds, /onboard branches on
// whether the instructor already has a real email on file.
//
//   Branch A — no real email (NULL, or an importer placeholder ending in
//     @import.placeholder.local): a combined email + confirm-email + password +
//     confirm-password form, one submit, no magic-link round-trip.
//   Branch B — a real email already exists: no form at all. A message plus
//     links to Forgot Password and Login. The real email is never shown.
import { test, expect } from './fixtures.js'
import { createTestStudio } from './helpers/studios.js'

async function adminHeaders(request) {
  const res = await request.post('http://localhost:8000/api/auth/login', {
    data: { email: 'admin@example.com', password: 'admin123' },
  })
  expect(res.ok()).toBeTruthy()
  return { Authorization: `Bearer ${(await res.json()).access_token}` }
}

async function studioWithCode(request, label) {
  const headers = await adminHeaders(request)
  const studio = await createTestStudio(request, label, headers)
  const detail = await request.get(`http://localhost:8000/api/studios/${studio.id}`, { headers })
  const code = (await detail.json()).onboard_code
  expect(code, 'studio should have an onboard code').toBeTruthy()
  return { studio, code, headers }
}

// Creates an unclaimed instructor (no password set) in the given studio, with
// either no email (Branch A — `email: null`) or a real one (Branch B), and a
// known PIN so the test can drive the PIN-entry step.
async function createUnclaimedInstructor(request, headers, { studioId, name, email, pin }) {
  const res = await request.post('http://localhost:8000/api/users', {
    headers,
    data: { name, email: email ?? null, role: 'instructor', studio_id: studioId },
  })
  if (!res.ok()) {
    throw new Error(`createUnclaimedInstructor(${name}) failed: ${res.status()} ${await res.text()}`)
  }
  const user = await res.json()
  const pinRes = await request.put(`http://localhost:8000/api/users/${user.id}/pin`, {
    headers, data: { pin },
  })
  expect(pinRes.ok()).toBeTruthy()
  return user
}

async function enterCodeAndPickName(page, code, instructorName) {
  await page.goto(`/onboard?studio=${encodeURIComponent(code)}`)
  const option = page.locator('[data-testid="onboard-instructor-option"]', { hasText: instructorName })
  await expect(option).toBeVisible({ timeout: 15000 })
  await option.click()
  await expect(page.locator('[data-testid="onboard-pin-step"]')).toBeVisible()
}

async function enterPin(page, pin) {
  await page.click('[data-testid="onboard-pin-toggle-mode"]')
  await page.fill('[data-testid="onboard-pin-text-input"]', pin)
  await page.click('[data-testid="onboard-pin-submit"]')
}

test.describe('B10: Branch A — placeholder/no email, combined setup form', () => {
  test('renders all four inputs and never shows an importer placeholder', async ({ page, request }) => {
    const { studio, code, headers } = await studioWithCode(request, 'b10-branch-a')
    const name = `Branch A Instructor ${Date.now()}`
    await createUnclaimedInstructor(request, headers, { studioId: studio.id, name, email: null, pin: '1357' })

    await enterCodeAndPickName(page, code, name)
    await enterPin(page, '1357')

    await expect(page.locator('[data-testid="onboard-setup-step"]')).toBeVisible()
    await expect(page.locator('[data-testid="onboard-email-input"]')).toBeVisible()
    await expect(page.locator('[data-testid="onboard-email-confirm-input"]')).toBeVisible()
    await expect(page.locator('[data-testid="onboard-password-input"]')).toBeVisible()
    await expect(page.locator('[data-testid="onboard-password-confirm-input"]')).toBeVisible()
    await expect(page.locator('[data-testid="onboard-already-active"]')).toHaveCount(0)

    const body = await page.locator('body').textContent()
    expect(body).not.toContain('import.placeholder.local')
  })

  test('client-side validation catches mismatched emails, short and mismatched passwords', async ({ page, request }) => {
    const { studio, code, headers } = await studioWithCode(request, 'b10-branch-a-validate')
    const name = `Branch A Validate ${Date.now()}`
    await createUnclaimedInstructor(request, headers, { studioId: studio.id, name, email: null, pin: '2468' })

    await enterCodeAndPickName(page, code, name)
    await enterPin(page, '2468')
    await expect(page.locator('[data-testid="onboard-setup-step"]')).toBeVisible()

    // Mismatched emails
    await page.fill('[data-testid="onboard-email-input"]', 'a@example.com')
    await page.fill('[data-testid="onboard-email-confirm-input"]', 'b@example.com')
    await page.fill('[data-testid="onboard-password-input"]', 'longenough1')
    await page.fill('[data-testid="onboard-password-confirm-input"]', 'longenough1')
    await page.click('[data-testid="onboard-setup-submit"]')
    await expect(page.locator('[data-testid="onboard-error-message"]')).toContainText("don't match")

    // Short password
    await page.fill('[data-testid="onboard-email-confirm-input"]', 'a@example.com')
    await page.fill('[data-testid="onboard-password-input"]', 'short')
    await page.fill('[data-testid="onboard-password-confirm-input"]', 'short')
    await page.click('[data-testid="onboard-setup-submit"]')
    await expect(page.locator('[data-testid="onboard-error-message"]')).toContainText('at least 8 characters')

    // Mismatched passwords
    await page.fill('[data-testid="onboard-password-input"]', 'longenough1')
    await page.fill('[data-testid="onboard-password-confirm-input"]', 'longenough2')
    await page.click('[data-testid="onboard-setup-submit"]')
    await expect(page.locator('[data-testid="onboard-error-message"]')).toContainText("don't match")

    // Still on the setup form — none of the above should have submitted
    await expect(page.locator('[data-testid="onboard-setup-step"]')).toBeVisible()
  })

  test('completing setup activates the account and the new credentials can sign in', async ({ page, request }) => {
    const { studio, code, headers } = await studioWithCode(request, 'b10-branch-a-complete')
    const name = `Branch A Complete ${Date.now()}`
    await createUnclaimedInstructor(request, headers, { studioId: studio.id, name, email: null, pin: '3579' })

    const newEmail = `b10-${Date.now()}@example.com`
    const newPassword = 'a-fresh-password-1'

    await enterCodeAndPickName(page, code, name)
    await enterPin(page, '3579')
    await expect(page.locator('[data-testid="onboard-setup-step"]')).toBeVisible()

    await page.fill('[data-testid="onboard-email-input"]', newEmail)
    await page.fill('[data-testid="onboard-email-confirm-input"]', newEmail)
    await page.fill('[data-testid="onboard-password-input"]', newPassword)
    await page.fill('[data-testid="onboard-password-confirm-input"]', newPassword)
    await page.click('[data-testid="onboard-setup-submit"]')

    await expect(page.locator('[data-testid="onboard-confirmation"]')).toBeVisible({ timeout: 15000 })
    await expect(page.locator('[data-testid="onboard-confirmation"]')).toContainText(newEmail)

    // The new credentials work immediately — no email round-trip.
    const loginRes = await request.post('http://localhost:8000/api/auth/login', {
      data: { email: newEmail, password: newPassword },
    })
    expect(loginRes.ok()).toBeTruthy()
  })
})

test.describe('B10: Branch B — real email already on file, no setup form', () => {
  test('shows the already-active message with no password inputs and no email input, and never shows the real email', async ({ page, request }) => {
    const { studio, code, headers } = await studioWithCode(request, 'b10-branch-b')
    const name = `Branch B Instructor ${Date.now()}`
    const realEmail = `already-real-${Date.now()}@example.com`
    await createUnclaimedInstructor(request, headers, { studioId: studio.id, name, email: realEmail, pin: '4680' })

    await enterCodeAndPickName(page, code, name)
    await enterPin(page, '4680')

    await expect(page.locator('[data-testid="onboard-already-active"]')).toBeVisible()
    await expect(page.locator('[data-testid="onboard-setup-step"]')).toHaveCount(0)
    await expect(page.locator('input[type="password"]')).toHaveCount(0)
    await expect(page.locator('[data-testid="onboard-email-input"]')).toHaveCount(0)

    const body = await page.locator('body').textContent()
    expect(body).not.toContain(realEmail)
  })

  test('both links navigate correctly', async ({ page, request }) => {
    const { studio, code, headers } = await studioWithCode(request, 'b10-branch-b-links')
    const name = `Branch B Links ${Date.now()}`
    const realEmail = `already-real-links-${Date.now()}@example.com`
    await createUnclaimedInstructor(request, headers, { studioId: studio.id, name, email: realEmail, pin: '5791' })

    await enterCodeAndPickName(page, code, name)
    await enterPin(page, '5791')
    await expect(page.locator('[data-testid="onboard-already-active"]')).toBeVisible()

    // The wizard's step is in-memory (not URL-persisted), so a real click +
    // browser-back loses it and re-runs the flow from step 1 — not what this
    // test is checking. Assert the hrefs directly instead, then confirm one
    // click actually lands (same pattern as signin-doors.spec.js).
    await expect(page.locator('[data-testid="onboard-goto-forgot-password"]')).toHaveAttribute('href', '/forgot-password')
    await expect(page.locator('[data-testid="onboard-goto-login"]')).toHaveAttribute('href', '/login')

    await page.click('[data-testid="onboard-goto-forgot-password"]')
    await expect(page).toHaveURL(/\/forgot-password$/)
  })
})
