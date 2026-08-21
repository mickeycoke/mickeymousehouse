import client from './client'

// Admin pricing-tier price book — the ladder itself (Free/Essential/Studio/
// Growth/Scale/Scale Plus/Elite/Enterprise), NOT an individual studio's
// Stripe subscription (see studioBilling.js for that). See
// backend/app/routes/pricing_tiers.py.
// Admin-only, matching the backend's Depends(require_admin) on every route.
const PRICING_TIERS_PATH = '/admin/pricing-tiers'
const pricingTierPath = (id) => `${PRICING_TIERS_PATH}/${id}`

// GET /api/admin/pricing-tiers — every tier, sorted by display_order.
export async function listPricingTiers() {
  const { data } = await client.get(PRICING_TIERS_PATH)
  return data
}

// POST /api/admin/pricing-tiers — create a new tier.
export async function createPricingTier(payload) {
  const { data } = await client.post(PRICING_TIERS_PATH, payload)
  return data
}

// PUT /api/admin/pricing-tiers/{id} — update any subset of fields.
export async function updatePricingTier(id, payload) {
  const { data } = await client.put(pricingTierPath(id), payload)
  return data
}

// DELETE /api/admin/pricing-tiers/{id} — soft delete (is_active=false).
export async function deletePricingTier(id) {
  const { data } = await client.delete(pricingTierPath(id))
  return data
}
