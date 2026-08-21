import client from './client'

// Self-serve owner Billing tab — a studio/
// franchise owner's own view of their studio(s)' subscription, separate
// from the admin-only central roster in studioBilling.js. See
// backend/app/routes/owner_billing.py.
const BASE = '/billing/my-studios'

// GET /api/billing/my-studios — every studio this user owns (owner-level,
// including a franchise owner's studios), each with status + what action
// (if any) is available.
export async function listMyBillingStudios() {
  const { data } = await client.get(BASE)
  return data
}

// POST /api/billing/my-studios/{id}/checkout-session — self-serve: start or
// resume billing (requires an admin to have already set a price). Returns
// { checkout_url }.
export async function createMyCheckout(studioId) {
  const { data } = await client.post(`${BASE}/${studioId}/checkout-session`)
  return data
}

// POST /api/billing/my-studios/{id}/billing-portal-session — self-serve:
// fix a failed payment method via Stripe's own Billing Portal. Returns
// { checkout_url } (a portal URL, same response shape).
export async function createMyBillingPortalSession(studioId) {
  const { data } = await client.post(`${BASE}/${studioId}/billing-portal-session`)
  return data
}
