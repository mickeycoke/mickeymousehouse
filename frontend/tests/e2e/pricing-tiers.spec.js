// Pricing tiers admin UI — a standalone price BOOK page,
// NOT the existing /setup/billing screen (that's one studio's Stripe
// subscription; see studio-billing.spec.js). This page is a reference/config
// table an admin views and edits.
//
// Coverage: the 8 seeded tiers load with correct values, editing a tier
// recomputes $/client-at-cap live (client-side, before any save round trip),
// a save persists across reload, and a non-admin cannot reach the page.
import { test, expect } from './fixtures.js'

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

function tierRow(page, name) {
  return page.locator('[data-testid="pricing-tier-row"]', { hasText: name })
}

test.describe('Pricing tiers — seeded price book', () => {
  test.beforeEach(async ({ page }) => {
    await loginAdmin(page)
    await page.goto('/setup/pricing-tiers')
    await expect(page.locator('[data-testid="pricing-tiers-page"]')).toBeVisible()
  })

  test('the Manage dashboard has a Pricing tiers card that links here', async ({ page }) => {
    await page.goto('/setup')
    await expect(page.locator('[data-testid="setup-nav-pricing-tiers"]')).toBeVisible()
    await page.click('[data-testid="setup-nav-pricing-tiers"]')
    await expect(page).toHaveURL(/\/setup\/pricing-tiers/)
    await expect(page.locator('[data-testid="pricing-tiers-page"]')).toBeVisible()
  })

  test('all 8 seeded tiers load with the right names, ranges, and prices', async ({ page }) => {
    const names = ['Free', 'Essential', 'Studio', 'Growth', 'Scale Plus', 'Elite', 'Enterprise']
    for (const name of names) {
      await expect(tierRow(page, name)).toBeVisible()
    }
    // "Scale" alone would also match "Scale Plus" via substring text search,
    // so pin it down with an exact-name locator instead of tierRow().
    await expect(
      page.locator('[data-testid="pricing-tier-row"]').filter({ has: page.locator('[data-testid="pricing-tier-name"]', { hasText: /^Scale$/ }) })
    ).toBeVisible()

    // Free: 0-1 clients, $0, and therefore $0.00/client (0 is a real price,
    // not the "custom" null).
    const free = tierRow(page, 'Free')
    await expect(free.locator('[data-testid="pricing-tier-min-clients"]')).toHaveText('0')
    await expect(free.locator('[data-testid="pricing-tier-max-clients"]')).toHaveText('1')
    await expect(free.locator('[data-testid="pricing-tier-price"]')).toHaveText('$0.00')
    await expect(free.locator('[data-testid="pricing-tier-per-client-rate"]')).toHaveText('$0.00/client')

    // Essential: the exact worked example from the API contract —
    // 4000 cents / 100 / 30 clients = $1.33/client.
    const essential = tierRow(page, 'Essential')
    await expect(essential.locator('[data-testid="pricing-tier-min-clients"]')).toHaveText('2')
    await expect(essential.locator('[data-testid="pricing-tier-max-clients"]')).toHaveText('30')
    await expect(essential.locator('[data-testid="pricing-tier-price"]')).toHaveText('$40.00')
    await expect(essential.locator('[data-testid="pricing-tier-per-client-rate"]')).toHaveText('$1.33/client')

    // Enterprise: open-ended and custom-priced — both nulls render as their
    // own placeholders, not as $0 or a computed rate.
    const enterprise = tierRow(page, 'Enterprise')
    await expect(enterprise.locator('[data-testid="pricing-tier-min-clients"]')).toHaveText('301')
    await expect(enterprise.locator('[data-testid="pricing-tier-max-clients"]')).toHaveText('No limit')
    await expect(enterprise.locator('[data-testid="pricing-tier-price"]')).toHaveText('Custom')
    await expect(enterprise.locator('[data-testid="pricing-tier-per-client-rate"]')).toHaveText('--')
  })
})

test.describe('Pricing tiers — live recompute, save, and reload', () => {
  test('editing price/max recomputes $/client live, and saving persists across reload', async ({ page, request }) => {
    const headers = await adminHeaders(request)
    const ts = Date.now()
    const name = `E2E Tier ${ts}`

    // Seed a dedicated tier via the real API so this test never touches the
    // shared seed rows (which the "seeded price book" describe block above
    // asserts exact values against).
    const created = await request.post(`${API}/api/admin/pricing-tiers`, {
      headers,
      data: { name, min_clients: 1, max_clients: 50, monthly_price_cents: 5000, display_order: 9999 },
    })
    expect(created.ok(), 'seed pricing tier must succeed').toBeTruthy()
    const { id: tierId } = await created.json()

    await loginAdmin(page)
    await page.goto('/setup/pricing-tiers')
    // Keyed off data-tier-id, not the visible name — once editing starts the
    // name moves into an <input> VALUE, which a text-based locator can't see
    // (Playwright's hasText reads rendered text content, not input values),
    // so a name-based locator would go stale the instant Edit is clicked.
    const row = page.locator(`[data-testid="pricing-tier-row"][data-tier-id="${tierId}"]`)
    await expect(row).toBeVisible()
    // 5000 cents / 100 / 50 = $1.00/client to start.
    await expect(row.locator('[data-testid="pricing-tier-per-client-rate"]')).toHaveText('$1.00/client')

    await row.locator('[data-testid="pricing-tier-edit-button"]').click()
    const priceInput = row.locator('[data-testid="pricing-tier-price-input"]')
    await expect(priceInput).toHaveValue('50.00')

    // Change the price only — before Save is clicked, nothing has round-
    // tripped to the server, so this proves the recompute is client-side.
    await priceInput.fill('100')
    await expect(row.locator('[data-testid="pricing-tier-per-client-rate"]')).toHaveText('$2.00/client')

    // Change max_clients too, still unsaved.
    const maxInput = row.locator('[data-testid="pricing-tier-max-clients-input"]')
    await maxInput.fill('25')
    await expect(row.locator('[data-testid="pricing-tier-per-client-rate"]')).toHaveText('$4.00/client')

    await row.locator('[data-testid="pricing-tier-save-button"]').click()
    await expect(row.locator('[data-testid="pricing-tier-edit-button"]')).toBeVisible({ timeout: 10000 })
    await expect(row.locator('[data-testid="pricing-tier-price"]')).toHaveText('$100.00')
    await expect(row.locator('[data-testid="pricing-tier-max-clients"]')).toHaveText('25')
    await expect(row.locator('[data-testid="pricing-tier-per-client-rate"]')).toHaveText('$4.00/client')

    // Reload — the new value must have actually persisted server-side, not
    // just be sitting in local component state.
    await page.reload()
    const reloadedRow = tierRow(page, name)
    await expect(reloadedRow).toBeVisible()
    await expect(reloadedRow.locator('[data-testid="pricing-tier-price"]')).toHaveText('$100.00')
    await expect(reloadedRow.locator('[data-testid="pricing-tier-max-clients"]')).toHaveText('25')
    await expect(reloadedRow.locator('[data-testid="pricing-tier-per-client-rate"]')).toHaveText('$4.00/client')

    // Clean up — deactivate through the real UI flow (also exercises the
    // confirm dialog) rather than leaving a stray test tier behind.
    await reloadedRow.locator('[data-testid="pricing-tier-deactivate-button"]').click()
    await page.click('[data-testid="pricing-tier-deactivate-confirm-button"]')
    await expect(reloadedRow.locator('[data-testid="pricing-tier-status-badge"]')).toHaveText('Inactive')
  })

  test('Add tier defaults display_order to one past the current max and creates a new row', async ({ page, request }) => {
    const headers = await adminHeaders(request)
    // workers: 1 in playwright.config.js — no other spec can add a tier
    // between this read and the UI create below, so the expected order is
    // stable to compute up front.
    const before = await (await request.get(`${API}/api/admin/pricing-tiers`, { headers })).json()
    const expectedOrder = Math.max(...before.map((t) => t.display_order ?? 0)) + 1

    await loginAdmin(page)
    await page.goto('/setup/pricing-tiers')

    const ts = Date.now()
    const name = `E2E Added ${ts}`

    await page.click('[data-testid="pricing-tiers-add-button"]')
    const newRow = page.locator('[data-testid="pricing-tier-row"][data-tier-id="new"]')
    await expect(newRow).toBeVisible()

    await newRow.locator('[data-testid="pricing-tier-name-input"]').fill(name)
    await newRow.locator('[data-testid="pricing-tier-min-clients-input"]').fill('1')
    await newRow.locator('[data-testid="pricing-tier-max-clients-input"]').fill('10')
    await newRow.locator('[data-testid="pricing-tier-price-input"]').fill('20')
    await expect(newRow.locator('[data-testid="pricing-tier-per-client-rate"]')).toHaveText('$2.00/client')

    await newRow.locator('[data-testid="pricing-tier-save-button"]').click()
    const savedRow = tierRow(page, name)
    await expect(savedRow).toBeVisible()
    await expect(savedRow.locator('[data-testid="pricing-tier-price"]')).toHaveText('$20.00')

    const after = await (await request.get(`${API}/api/admin/pricing-tiers`, { headers })).json()
    const createdTier = after.find((t) => t.name === name)
    expect(createdTier.display_order).toBe(expectedOrder)

    // Clean up.
    await savedRow.locator('[data-testid="pricing-tier-deactivate-button"]').click()
    await page.click('[data-testid="pricing-tier-deactivate-confirm-button"]')
  })
})

test.describe('Pricing tiers — admin-only access', () => {
  test('a non-admin instructor cannot reach the pricing tiers page', async ({ page, request }) => {
    const headers = await adminHeaders(request)
    const ts = Date.now()
    const email = `e2e-pricing-instructor-${ts}@example.com`
    const created = await request.post(`${API}/api/users`, {
      headers,
      data: { name: `E2E Pricing Instructor ${ts}`, email, password: 'password123', role: 'instructor' },
    })
    expect(created.ok(), 'instructor seed user must succeed').toBeTruthy()

    await page.goto('/login')
    await page.fill('[data-testid="login-email-input"]', email)
    await page.fill('[data-testid="login-password-input"]', 'password123')
    await page.click('[data-testid="login-submit-button"]')
    await expect(page).toHaveURL(/\/admin\/overview/, { timeout: 30000 })

    // RequireAdmin (the same gate /setup/billing and /setup/client-exercise-
    // settings use) bounces a non-admin back to /admin/overview.
    await page.goto('/setup/pricing-tiers')
    await expect(page).toHaveURL(/\/admin\/overview/, { timeout: 30000 })
    await expect(page.locator('[data-testid="pricing-tiers-page"]')).toHaveCount(0)

    // The Manage dashboard must not even offer the card to a non-admin.
    await page.goto('/setup')
    await expect(page.locator('[data-testid="setup-nav-pricing-tiers"]')).toHaveCount(0)
  })
})
