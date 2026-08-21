import client from './client'

// Stripe Studio Billing — the platform's OWN revenue: a studio pays a
// recurring monthly subscription. Separate from Client Payments
// (clientPackages.js) — see backend/app/routes/studio_billing.py.
// Admin-only except the config gate.
const BILLING_BASE = '/admin/billing'
const billingStudioPath = (studioId) => `${BILLING_BASE}/studios/${studioId}`

// GET /api/admin/billing/config — the small global on/off gate (no auth).
// Returns { enabled }. The frontend reads this before rendering any billing
// UI, mirroring getPaymentsConfig().
export async function getBillingConfig() {
  const { data } = await client.get(`${BILLING_BASE}/config`)
  return data
}

// GET /api/admin/billing/studios — every studio with its (possibly
// not-yet-started) subscription row: contracted amount, status, next payment.
// franchiseId: optional — narrows the roster to
// studios linked to that franchise. Omitted/falsy = every active studio.
export async function listBillingStudios(franchiseId) {
  const { data } = await client.get(`${BILLING_BASE}/studios`, {
    params: franchiseId ? { franchise_id: franchiseId } : {},
  })
  return data
}

// POST /api/admin/billing/studios/{id}/contracted-amount — set the price an
// admin has agreed with a studio. amountCents is an integer (cents).
export async function setContractedAmount(studioId, amountCents, currency = 'usd') {
  const { data } = await client.post(`${billingStudioPath(studioId)}/contracted-amount`, {
    amount_cents: amountCents,
    currency,
  })
  return data
}

// POST /api/admin/billing/studios/{id}/checkout-session — start a Stripe
// subscription Checkout for this studio. Returns { checkout_url }. Requires a
// contracted amount to already be set (server enforces this).
export async function createBillingCheckout(studioId) {
  const { data } = await client.post(`${billingStudioPath(studioId)}/checkout-session`)
  return data
}
