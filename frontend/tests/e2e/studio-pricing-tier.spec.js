// Studio <-> pricing tier assignment — an admin labels a
// studio with a price-book tier (see pricing-tiers.spec.js for the price
// book itself) from the existing Studios edit modal
// (frontend/src/pages/ownership/StudiosPage.jsx). Purely a label: does not
// touch StudioSubscription.contracted_amount_cents or any billing flow.
//
// Coverage: the dropdown lists all active pricing tiers (plus "No tier
// assigned"), assigning a tier persists across reload, the studio's current
// tier is pre-selected correctly when revisiting the page, and reassigning
// to a different tier and reloading shows the new one.
import { test, expect } from './fixtures.js'
import { createTestStudio } from './helpers/studios.js'

const API = 'http://localhost:8000'

async function adminHeaders(request) {
  const res = await request.post(`${API}/api/auth/login`, {
    data: { email: 'admin@example.com', password: 'admin123' },
  })
  expect(res.ok(), 'admin login must succeed').toBeTruthy()
  return { Authorization: `Bearer ${(await res.json()).access_token}` }
}

async function loginAdmin(page) {
  await page.goto('/login')
  await page.fill('[data-testid="login-email-input"]', 'admin@example.com')
  await page.fill('[data-testid="login-password-input"]', 'admin123')
  await page.click('[data-testid="login-submit-button"]')
  await expect(page).toHaveURL(/\/admin\/overview/, { timeout: 30000 })
}

function studioRow(page, name) {
  return page.locator('[data-testid="studio-row"]', { hasText: name })
}

async function openEdit(page, name) {
  const row = studioRow(page, name)
  await expect(row).toBeVisible()
  await row.locator('[data-testid="studio-edit-button"]').click()
  await expect(page.locator('[data-testid="studio-pricing-tier-select"]')).toBeVisible()
}

async function saveAndWaitForClose(page) {
  await page.click('[data-testid="studio-save-button"]')
  await expect(page.locator('[data-testid="studio-save-button"]')).toHaveCount(0)
}

test.describe('Studio pricing tier assignment', () => {
  test('lists active tiers, pre-selects the current one, persists an assignment, and persists a reassignment', async ({ page, request }) => {
    const headers = await adminHeaders(request)
    const studio = await createTestStudio(request, 'pricing-tier', headers)

    // Seed two dedicated tiers via the real API so this test never touches
    // the shared 8-tier seed (pricing-tiers.spec.js's "seeded price book"
    // block asserts exact values against those).
    const ts = Date.now()
    const tierAName = `E2E PT Tier A ${ts}`
    const tierBName = `E2E PT Tier B ${ts}`
    const tierARes = await request.post(`${API}/api/admin/pricing-tiers`, {
      headers,
      data: { name: tierAName, min_clients: 1, max_clients: 30, monthly_price_cents: 4000, display_order: 9990 },
    })
    expect(tierARes.ok(), 'seed tier A must succeed').toBeTruthy()
    const tierA = await tierARes.json()
    const tierBRes = await request.post(`${API}/api/admin/pricing-tiers`, {
      headers,
      data: { name: tierBName, min_clients: 31, max_clients: null, monthly_price_cents: null, display_order: 9991 },
    })
    expect(tierBRes.ok(), 'seed tier B must succeed').toBeTruthy()
    const tierB = await tierBRes.json()

    try {
      await loginAdmin(page)
      await page.goto('/studios')
      await expect(page.locator('[data-testid="studios-page"]')).toBeVisible()

      await openEdit(page, studio.name)
      const select = page.locator('[data-testid="studio-pricing-tier-select"]')

      // Brand-new studio starts with no tier assigned.
      await expect(select).toHaveValue('')

      // Every active tier shows up as an option, labeled "Name ($X/mo)" or
      // "Name (Custom)" for a null (negotiated) price, plus the placeholder.
      const optionTexts = await select.locator('option').allTextContents()
      expect(optionTexts).toContain('No tier assigned')
      expect(optionTexts).toContain(`${tierAName} ($40/mo)`)
      expect(optionTexts).toContain(`${tierBName} (Custom)`)

      // Assign tier A and save.
      await select.selectOption(tierA.id)
      await saveAndWaitForClose(page)

      // Reload the whole page (not just re-render) — the assignment must
      // have actually round-tripped through the server, and the edit modal
      // must pre-select it correctly on a fresh visit.
      await page.reload()
      await expect(page.locator('[data-testid="studios-page"]')).toBeVisible()
      await openEdit(page, studio.name)
      await expect(page.locator('[data-testid="studio-pricing-tier-select"]')).toHaveValue(tierA.id)

      // Reassign to tier B and confirm that persists too.
      await page.locator('[data-testid="studio-pricing-tier-select"]').selectOption(tierB.id)
      await saveAndWaitForClose(page)

      await page.reload()
      await expect(page.locator('[data-testid="studios-page"]')).toBeVisible()
      await openEdit(page, studio.name)
      await expect(page.locator('[data-testid="studio-pricing-tier-select"]')).toHaveValue(tierB.id)
    } finally {
      // Clean up the seeded tiers regardless of test outcome.
      await request.delete(`${API}/api/admin/pricing-tiers/${tierA.id}`, { headers })
      await request.delete(`${API}/api/admin/pricing-tiers/${tierB.id}`, { headers })
    }
  })
})
