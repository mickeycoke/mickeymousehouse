import { useEffect, useState } from 'react'
import AppShell from '../../components/layout/AppShell'
import SetupPageShell from '../../components/setup/SetupPageShell'
import { SetupLoading, SetupError } from '../../components/setup/SetupStates'
import Button from '../../components/ui/Button'
import Modal from '../../components/ui/Modal'
import {
  listPricingTiers,
  createPricingTier,
  updatePricingTier,
  deletePricingTier,
} from '../../api/pricingTiers'
import { getApiErrorMessage } from '../../utils/apiError'

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function formatMaxClients(maxClients) {
  return maxClients == null ? 'No limit' : String(maxClients)
}

function formatPrice(cents) {
  if (cents == null) return 'Custom'
  return `$${(cents / 100).toFixed(2)}`
}

function formatRate(rate) {
  return rate == null ? '--' : `$${rate.toFixed(2)}/client`
}

// Same computation the backend does — monthly price in dollars divided by
// the tier's client cap, rounded to 2 decimals. Runs client-side, live, off
// whatever is currently typed into the form (not the last-saved row), so the
// admin sees the effect of an edit before saving it, not after a round trip.
function computeLiveRate(priceDollarsInput, maxClientsInput) {
  if (priceDollarsInput === '' || priceDollarsInput == null) return null
  if (maxClientsInput === '' || maxClientsInput == null) return null
  const price = Number(priceDollarsInput)
  const max = Number(maxClientsInput)
  if (!Number.isFinite(price) || !Number.isFinite(max) || max <= 0) return null
  return Math.round((price / max) * 100) / 100
}

function emptyFormFromTier(tier) {
  return {
    name: tier?.name ?? '',
    minClients: tier?.min_clients ?? '',
    maxClients: tier?.max_clients ?? '',
    maxUnlimited: tier ? tier.max_clients == null : false,
    priceDollars: tier?.monthly_price_cents != null ? (tier.monthly_price_cents / 100).toFixed(2) : '',
    priceCustom: tier ? tier.monthly_price_cents == null : false,
  }
}

// ---------------------------------------------------------------------------
// One row — either an existing tier (viewable, editable in place) or the
// blank "new tier" row opened by the Add tier button. Self-contained local
// form state, same pattern as BillingStudioRow in BillingPage.jsx, so a save
// here only re-renders this row and its parent's list. Deactivation is
// confirmed by a single Modal owned by the page (see PricingTiersPage) —
// same split UsersPage uses for its delete-user confirm — rather than one
// Modal per row, so the table never nests a `position:fixed` overlay inside
// a `<tr>`.
// ---------------------------------------------------------------------------
function PricingTierRow({ tier, isNew, defaultDisplayOrder, onSaved, onCreated, onCancelNew, onRequestDeactivate, onReactivated }) {
  const [editing, setEditing] = useState(isNew)
  const [form, setForm] = useState(() => emptyFormFromTier(tier))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  function startEdit() {
    setForm(emptyFormFromTier(tier))
    setError(null)
    setEditing(true)
  }

  function cancelEdit() {
    if (isNew) {
      onCancelNew()
      return
    }
    setForm(emptyFormFromTier(tier))
    setError(null)
    setEditing(false)
  }

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  function buildPayload() {
    const name = form.name.trim()
    if (!name) return { fieldError: 'Name is required' }

    const minClients = Number(form.minClients)
    if (form.minClients === '' || !Number.isFinite(minClients) || minClients < 0) {
      return { fieldError: 'Min clients must be 0 or greater' }
    }

    let maxClients = null
    if (!form.maxUnlimited) {
      maxClients = Number(form.maxClients)
      if (form.maxClients === '' || !Number.isFinite(maxClients) || maxClients < 0) {
        return { fieldError: 'Max clients must be 0 or greater, or marked "No limit"' }
      }
    }

    let monthlyPriceCents = null
    if (!form.priceCustom) {
      const priceDollars = Number(form.priceDollars)
      if (form.priceDollars === '' || !Number.isFinite(priceDollars) || priceDollars < 0) {
        return { fieldError: 'Monthly price must be 0 or greater, or marked "Custom"' }
      }
      monthlyPriceCents = Math.round(priceDollars * 100)
    }

    return {
      payload: {
        name,
        min_clients: Math.round(minClients),
        max_clients: maxClients == null ? null : Math.round(maxClients),
        monthly_price_cents: monthlyPriceCents,
      },
    }
  }

  async function handleSave() {
    const { fieldError, payload } = buildPayload()
    if (fieldError) {
      setError(fieldError)
      return
    }
    setSaving(true)
    setError(null)
    try {
      if (isNew) {
        const created = await createPricingTier({ ...payload, display_order: defaultDisplayOrder })
        onCreated(created)
      } else {
        const updated = await updatePricingTier(tier.id, payload)
        onSaved(updated)
        setEditing(false)
      }
    } catch (err) {
      setError(getApiErrorMessage(err, 'Could not save this tier'))
    } finally {
      setSaving(false)
    }
  }

  async function handleReactivate() {
    setSaving(true)
    setError(null)
    try {
      const updated = await updatePricingTier(tier.id, { is_active: true })
      onReactivated(updated)
    } catch (err) {
      setError(getApiErrorMessage(err, 'Could not reactivate this tier'))
    } finally {
      setSaving(false)
    }
  }

  const liveRate = editing
    ? computeLiveRate(form.priceCustom ? null : form.priceDollars, form.maxUnlimited ? null : form.maxClients)
    : (tier?.per_client_rate_at_cap ?? null)

  if (editing) {
    return (
      <tr data-testid="pricing-tier-row" data-tier-id={tier?.id ?? 'new'}>
        <td className="px-4 py-3 align-top">
          <input
            type="text"
            value={form.name}
            onChange={(e) => update('name', e.target.value)}
            placeholder="Tier name"
            data-testid="pricing-tier-name-input"
            className="w-32 rounded-lg border border-gray-300 px-2 py-1 text-sm"
          />
        </td>
        <td className="px-4 py-3 align-top">
          <input
            type="number"
            min="0"
            value={form.minClients}
            onChange={(e) => update('minClients', e.target.value)}
            data-testid="pricing-tier-min-clients-input"
            className="w-20 rounded-lg border border-gray-300 px-2 py-1 text-sm"
          />
        </td>
        <td className="px-4 py-3 align-top">
          <input
            type="number"
            min="0"
            value={form.maxUnlimited ? '' : form.maxClients}
            disabled={form.maxUnlimited}
            onChange={(e) => update('maxClients', e.target.value)}
            data-testid="pricing-tier-max-clients-input"
            className="w-20 rounded-lg border border-gray-300 px-2 py-1 text-sm disabled:bg-gray-100 disabled:text-gray-400"
          />
          <label className="mt-1 flex items-center gap-1.5 text-xs text-gray-500">
            <input
              type="checkbox"
              checked={form.maxUnlimited}
              onChange={(e) => update('maxUnlimited', e.target.checked)}
              data-testid="pricing-tier-max-clients-unlimited-checkbox"
              className="h-3.5 w-3.5 rounded border-gray-300"
            />
            No limit
          </label>
        </td>
        <td className="px-4 py-3 align-top">
          <div className="flex items-center gap-1">
            <span className="text-sm text-gray-500">$</span>
            <input
              type="number"
              min="0"
              step="0.01"
              value={form.priceCustom ? '' : form.priceDollars}
              disabled={form.priceCustom}
              onChange={(e) => update('priceDollars', e.target.value)}
              data-testid="pricing-tier-price-input"
              className="w-24 rounded-lg border border-gray-300 px-2 py-1 text-sm disabled:bg-gray-100 disabled:text-gray-400"
            />
          </div>
          <label className="mt-1 flex items-center gap-1.5 text-xs text-gray-500">
            <input
              type="checkbox"
              checked={form.priceCustom}
              onChange={(e) => update('priceCustom', e.target.checked)}
              data-testid="pricing-tier-price-custom-checkbox"
              className="h-3.5 w-3.5 rounded border-gray-300"
            />
            Custom
          </label>
        </td>
        <td className="px-4 py-3 align-top text-sm text-gray-700" data-testid="pricing-tier-per-client-rate">
          {formatRate(liveRate)}
        </td>
        <td className="px-4 py-3 align-top">
          <div className="flex flex-col gap-2">
            {error && <p className="text-xs text-red-600" data-testid="pricing-tier-row-error">{error}</p>}
            <div className="flex gap-2">
              <Button size="sm" variant="primary" testId="pricing-tier-save-button" loading={saving} disabled={saving} onClick={handleSave}>
                Save
              </Button>
              <Button size="sm" variant="secondary" testId="pricing-tier-cancel-button" disabled={saving} onClick={cancelEdit}>
                Cancel
              </Button>
            </div>
          </div>
        </td>
      </tr>
    )
  }

  return (
    <tr data-testid="pricing-tier-row" data-tier-id={tier.id}>
      <td className="px-4 py-3 text-sm font-medium text-gray-900" data-testid="pricing-tier-name">
        {tier.name}
        {!tier.is_active && (
          <span
            className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600"
            data-testid="pricing-tier-status-badge"
          >
            Inactive
          </span>
        )}
      </td>
      <td className="px-4 py-3 text-sm text-gray-700" data-testid="pricing-tier-min-clients">{tier.min_clients}</td>
      <td className="px-4 py-3 text-sm text-gray-700" data-testid="pricing-tier-max-clients">{formatMaxClients(tier.max_clients)}</td>
      <td className="px-4 py-3 text-sm text-gray-700" data-testid="pricing-tier-price">{formatPrice(tier.monthly_price_cents)}</td>
      <td className="px-4 py-3 text-sm text-gray-700" data-testid="pricing-tier-per-client-rate">{formatRate(liveRate)}</td>
      <td className="px-4 py-3">
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" testId="pricing-tier-edit-button" onClick={startEdit}>
            Edit
          </Button>
          {tier.is_active ? (
            <Button size="sm" variant="ghost" testId="pricing-tier-deactivate-button" onClick={() => onRequestDeactivate(tier)}>
              Deactivate
            </Button>
          ) : (
            <Button size="sm" variant="ghost" testId="pricing-tier-reactivate-button" loading={saving} disabled={saving} onClick={handleReactivate}>
              Reactivate
            </Button>
          )}
        </div>
        {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

// Admin-only price BOOK — the tier ladder itself (Free/Essential/Studio/
// Growth/Scale/Scale Plus/Elite/Enterprise). This is a sibling of
// /setup/billing, not a replacement — billing is one studio's Stripe
// subscription; this is the reference price list an admin quotes from. It
// does NOT wire into actual per-studio billing (studio_subscriptions stays
// hand-set) — this is reference/config only.
export default function PricingTiersPage() {
  const [tiers, setTiers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [addingNew, setAddingNew] = useState(false)

  const [confirmTarget, setConfirmTarget] = useState(null) // tier pending deactivation
  const [deactivating, setDeactivating] = useState(false)
  const [deactivateError, setDeactivateError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    listPricingTiers()
      .then((rows) => { if (!cancelled) setTiers(rows) })
      .catch((err) => { if (!cancelled) setError(getApiErrorMessage(err, 'Could not load pricing tiers')) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  function handleSaved(updated) {
    setTiers((rows) => rows.map((r) => (r.id === updated.id ? updated : r)).sort((a, b) => a.display_order - b.display_order))
  }

  function handleReactivated(updated) {
    setTiers((rows) => rows.map((r) => (r.id === updated.id ? updated : r)))
  }

  function handleCreated(created) {
    setTiers((rows) => [...rows, created].sort((a, b) => a.display_order - b.display_order))
    setAddingNew(false)
  }

  function closeConfirm() {
    setConfirmTarget(null)
    setDeactivateError(null)
  }

  async function handleConfirmDeactivate() {
    if (!confirmTarget) return
    setDeactivating(true)
    setDeactivateError(null)
    try {
      await deletePricingTier(confirmTarget.id)
      setTiers((rows) => rows.map((r) => (r.id === confirmTarget.id ? { ...r, is_active: false } : r)))
      setConfirmTarget(null)
    } catch (err) {
      setDeactivateError(getApiErrorMessage(err, 'Could not deactivate this tier'))
    } finally {
      setDeactivating(false)
    }
  }

  const nextDisplayOrder = tiers.length
    ? Math.max(...tiers.map((t) => t.display_order ?? 0)) + 1
    : 1

  return (
    <AppShell>
      <SetupPageShell
        title="Pricing tiers"
        subtitle="The price book — Free through Enterprise. Editing here does not change any studio's actual bill; see Billing for that."
        actions={
          <Button
            variant="primary"
            testId="pricing-tiers-add-button"
            disabled={addingNew}
            onClick={() => setAddingNew(true)}
          >
            + Add tier
          </Button>
        }
      >
        <div data-testid="pricing-tiers-page">
          {loading && <SetupLoading message="Loading pricing tiers…" />}

          {!loading && error && <SetupError message={error} onRetry={() => window.location.reload()} />}

          {!loading && !error && (
            <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Tier name</th>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Min clients</th>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Max clients</th>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Monthly price</th>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">$/client at cap</th>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {addingNew && (
                    <PricingTierRow
                      isNew
                      tier={null}
                      defaultDisplayOrder={nextDisplayOrder}
                      onCreated={handleCreated}
                      onCancelNew={() => setAddingNew(false)}
                    />
                  )}
                  {tiers.length === 0 && !addingNew && (
                    <tr>
                      <td colSpan={6} className="px-4 py-6 text-center text-sm text-gray-500">No pricing tiers found.</td>
                    </tr>
                  )}
                  {tiers.map((tier) => (
                    <PricingTierRow
                      key={tier.id}
                      tier={tier}
                      onSaved={handleSaved}
                      onRequestDeactivate={setConfirmTarget}
                      onReactivated={handleReactivated}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </SetupPageShell>

      <Modal
        isOpen={!!confirmTarget}
        onClose={closeConfirm}
        title="Deactivate pricing tier"
      >
        <p className="text-sm text-gray-600 mb-6">
          Deactivate <strong>{confirmTarget?.name}</strong>? Studios already on this tier keep their price — this
          just hides it from new assignment. You can reactivate it later.
        </p>
        {deactivateError && <p className="text-sm text-red-600 mb-4">{deactivateError}</p>}
        <div className="flex justify-end gap-3">
          <Button variant="secondary" testId="pricing-tier-deactivate-cancel-button" onClick={closeConfirm}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={deactivating}
            testId="pricing-tier-deactivate-confirm-button"
            onClick={handleConfirmDeactivate}
          >
            Deactivate
          </Button>
        </div>
      </Modal>
    </AppShell>
  )
}
