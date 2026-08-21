// "Existing Studios" — the three-screen route for a studio that is not
// signing in with an email and password.
//
// The flow:
//   sign-in screen — a NON-PROMINENT "Existing Studios" button
//     → enter your studio code
//     → PROMINENT "Shared Studio Device Login"
//       non-prominent "Studio Manager Administration"
//
// THE STUDIO CODE IS THE POINT OF ENTRY — the front desk must know it,
// and it is the point of entry for all studios. So the code comes FIRST, before
// either destination is offered, and is never bypassed or remembered on the
// device. An earlier attempt was about to cache it; these tests pin that it is
// asked for.
//
// Why this spec earns its runtime: /shared had NO link anywhere in the app —
// it was reachable only by typing the URL, which is no use to a front desk. A
// regression here is silent (the route keeps working) and invisible (nobody
// navigates to a URL they were never shown), so the links themselves need
// pinning, not just the pages behind them.
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
  // The onboard code is minted by the backend; read it back rather than
  // assuming a format.
  const detail = await request.get(`http://localhost:8000/api/studios/${studio.id}`, { headers })
  const code = (await detail.json()).onboard_code
  expect(code, 'studio should have an onboard code').toBeTruthy()
  return { studio, code }
}

async function enterCode(page, code) {
  await page.goto('/existing-studios')
  await page.fill('[data-testid="existing-studios-code-input"]', code)
  await page.click('[data-testid="existing-studios-code-submit"]')
  await expect(page.locator('[data-testid="existing-studios-options"]')).toBeVisible({ timeout: 15000 })
}

test.describe('Screen 1 — the sign-in screen', () => {
  test('carries ONE quiet Existing Studios button and nothing louder', async ({ page }) => {
    await page.goto('/login')
    const door = page.locator('[data-testid="login-existing-studios-link"]')
    await expect(door).toHaveText('Existing Studios')

    // Non-prominent is the design: email sign-in stays the filled primary,
    // this is an outline beneath it. Pinned by computed style so a restyle
    // cannot quietly promote it.
    const bg = await door.evaluate((el) => getComputedStyle(el).backgroundColor)
    expect(bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent' || bg === 'rgb(255, 255, 255)').toBeTruthy()

    // Earlier versions put the shared-device and admin links here directly.
    // If either returns to this screen it should be a decision, not a drift.
    await expect(page.locator('[data-testid="login-shared-device-link"]')).toHaveCount(0)
    await expect(page.locator('[data-testid="login-studio-manager-link"]')).toHaveCount(0)

    await door.click()
    await expect(page).toHaveURL(/\/existing-studios$/)
  })

  test('the whole route is reachable without being signed in', async ({ page }) => {
    // The point is serving people who CANNOT sign in yet. A stray
    // ProtectedRoute anywhere on this path would close the loop.
    await page.goto('/login')
    await page.evaluate(() => localStorage.clear())
    for (const path of ['/existing-studios', '/shared', '/onboard']) {
      await page.goto(path)
      await expect(page).toHaveURL(new RegExp(`${path}$`))
    }
  })
})

test.describe('Screen 2 — the studio code', () => {
  test('a wrong code is refused and reveals neither destination', async ({ page }) => {
    await page.goto('/existing-studios')
    await page.fill('[data-testid="existing-studios-code-input"]', 'NOSUCHCODE')
    await page.click('[data-testid="existing-studios-code-submit"]')

    await expect(page.locator('[data-testid="existing-studios-error"]')).toBeVisible({ timeout: 15000 })
    await expect(page.locator('[data-testid="existing-studios-options"]')).toHaveCount(0)
    await expect(page.locator('[data-testid="existing-studios-shared-device-link"]')).toHaveCount(0)
    await expect(page.locator('[data-testid="existing-studios-manager-admin-link"]')).toHaveCount(0)
  })

  test('Continue is inert until a code is typed', async ({ page }) => {
    await page.goto('/existing-studios')
    await expect(page.locator('[data-testid="existing-studios-code-submit"]')).toBeDisabled()
    await page.fill('[data-testid="existing-studios-code-input"]', 'X')
    await expect(page.locator('[data-testid="existing-studios-code-submit"]')).toBeEnabled()
  })

  test('the code field starts empty every time — never remembered', async ({ page, request }) => {
    // The front desk must know the code. Pins that a previous
    // device visit does not pre-fill it.
    const { code } = await studioWithCode(request, 'doors-nocache')
    await enterCode(page, code)
    await page.goto('/existing-studios')
    await expect(page.locator('[data-testid="existing-studios-code-input"]')).toHaveValue('')
  })
})

test.describe('Screen 3 — the two destinations', () => {
  test('names the studio, and the shared device is the prominent one', async ({ page, request }) => {
    const { studio, code } = await studioWithCode(request, 'doors-both')
    await enterCode(page, code)

    // Confirming the studio BY NAME is what the code step buys — it proves the
    // code resolved before anyone is sent onward with it.
    await expect(page.locator('body')).toContainText(studio.name)

    const shared = page.locator('[data-testid="existing-studios-shared-device-link"]')
    // "Studio Manager Administration" was removed from this screen
    // — it was a dead end here (login-gated, and the page
    // it led to excludes admin logins), replaced by the public Instructor
    // Setup link. Same prominence intent: the shared device is used every
    // day by every studio, instructor setup is an occasional errand.
    const instructorSetup = page.locator('[data-testid="existing-studios-instructor-setup-link"]')
    await expect(shared).toHaveText('Shared Studio Device Login')
    await expect(instructorSetup).toHaveText('Instructor Setup')

    // Measured so a restyle cannot quietly invert them.
    const sharedBox = await shared.boundingBox()
    const instructorSetupBox = await instructorSetup.boundingBox()
    expect(sharedBox.height).toBeGreaterThan(instructorSetupBox.height)
  })

  test('the validated code carries into the shared device login, past its own code step', async ({ page, request }) => {
    const { code } = await studioWithCode(request, 'doors-shared')
    await enterCode(page, code)

    const shared = page.locator('[data-testid="existing-studios-shared-device-link"]')
    await expect(shared).toHaveAttribute('href', `/shared?studio=${encodeURIComponent(code)}`)

    await shared.click()
    await expect(page).toHaveURL(new RegExp(`/shared\\?studio=${code}$`))
    // The code was just entered and validated one screen ago — asking for it a
    // second time would be the flow contradicting itself.
    await expect(page.locator('[data-testid="shared-code-input"]')).toHaveCount(0, { timeout: 15000 })
  })

  test('"Use a different studio code" returns to the code step', async ({ page, request }) => {
    const { code } = await studioWithCode(request, 'doors-swap')
    await enterCode(page, code)

    await page.click('[data-testid="existing-studios-change-studio"]')
    await expect(page.locator('[data-testid="existing-studios-code-input"]')).toBeVisible()
    await expect(page.locator('[data-testid="existing-studios-options"]')).toHaveCount(0)
  })
})
