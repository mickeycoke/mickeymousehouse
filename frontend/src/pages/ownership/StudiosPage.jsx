import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import AppShell from '../../components/layout/AppShell'
import PageHeader from '../../components/layout/PageHeader'
import Button from '../../components/ui/Button'
import Modal from '../../components/ui/Modal'
import { getStudios, createStudio, updateStudio } from '../../api/ownership'
import { getApiErrorMessage } from '../../utils/apiError'
import { TIMEZONES } from '../../utils/time'
import { getFranchises } from '../../api/ownership'
import { listPricingTiers } from '../../api/pricingTiers'
import { useAuth } from '../../context/AuthContext'
import { useOperatingStudio } from '../../context/StudioContext'
import { useOperatingFranchise } from '../../context/FranchiseContext'
import StudioPeopleInline from '../../components/ownership/StudioPeopleInline'
import StudioCodesModal from '../../components/ownership/StudioCodesModal'
import ConfirmDeactivateModal from '../../components/ui/ConfirmDeactivateModal'
import { IconChevronRight } from '@tabler/icons-react'

const EMPTY = { name: '', display_name: '', contact_name: '', contact_email: '', contact_phone: '', timezone: 'America/New_York', franchise_id: null, monthly_price: '', pricing_tier_id: null, address_line1: '', address_line2: '', city: '', state: '', postal_code: '', country: '' }

// Option label for the pricing-tier dropdown — tier name
// plus its price, e.g. "Essential ($40/mo)" / "Enterprise (Custom)" (a null
// monthly_price_cents is a deliberately unpriced/negotiated tier, same
// convention as PricingTiersPage's formatPrice, just condensed for a
// one-line option label instead of a table cell).
function formatTierOptionLabel(tier) {
  if (tier.monthly_price_cents == null) return `${tier.name} (Custom)`
  const dollars = tier.monthly_price_cents / 100
  const price = Number.isInteger(dollars) ? String(dollars) : dollars.toFixed(2)
  return `${tier.name} ($${price}/mo)`
}

// Studios management — franchise managers run the full studio lifecycle here
// (create, edit, contacts, deactivate), scoped server-side to their franchise.
export default function StudiosPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [studios, setStudios] = useState([])
  const [editing, setEditing] = useState(null)   // null | {id?} form values
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [showInactive, setShowInactive] = useState(false)
  const [search, setSearch] = useState('')
  const { isAdmin } = useAuth()
  const { setStudio } = useOperatingStudio()
  const { franchise: operatingFranchise, setFranchise, clearFranchise } = useOperatingFranchise()
  const [franchises, setFranchises] = useState([])
  const [pricingTiers, setPricingTiers] = useState([])
  const [codesStudio, setCodesStudio] = useState(null)   // studio whose QR/links modal is open
  const [pendingDeactivate, setPendingDeactivate] = useState(null)  // studio pending deactivation
  const [deactivating, setDeactivating] = useState(false)
  // Brief "Studio saved" confirmation — none of this
  // modal's fields (incl. the new pricing tier) show on the collapsed studio
  // row, so closing the modal alone gives no visible proof the save landed.
  const [savedBanner, setSavedBanner] = useState(false)
  const savedBannerTimeout = useRef(null)
  useEffect(() => () => clearTimeout(savedBannerTimeout.current), [])
  // The Franchise tab's selection pre-filters this page
  const [franchiseFilter, setFranchiseFilter] = useState(operatingFranchise?.id ?? '')

  function changeFranchiseFilter(id) {
    setFranchiseFilter(id)
    if (!id) { clearFranchise(); return }
    const f = franchises.find((x) => x.id === id)
    setFranchise({ id, name: f?.name ?? '' })
  }

  // Admin: entering a studio scopes the whole app to it. Reload so every screen
  // refetches at the new scope (the api client sends X-Studio-Id from here on).
  function selectStudio(s) {
    setStudio({ id: s.id, name: s.display_name || s.name })
    window.location.href = '/admin/overview'
  }

  function reload() {
    // The switcher itself must list every studio (allStudios) so you can change
    // scope even while an operating studio is selected. Returns its promise so
    // handleSave can await a fresh list before closing the modal — otherwise
    // reopening Edit right after Save can show the pre-save row (the "Edit"
    // button's onClick closes over the studios array at render time).
    return getStudios({ includeInactive: showInactive, franchiseId: franchiseFilter || null, allStudios: true })
      .then(setStudios).catch(() => setStudios([]))
  }
  // Not `useEffect(reload, ...)` directly — reload() now returns a promise
  // (so handleSave can await a fresh list before closing the modal), and a
  // useEffect callback must return undefined or a cleanup function, never a
  // promise. Wrapping it discards that return value for the effect.
  useEffect(() => { reload() }, [showInactive, franchiseFilter])

  useEffect(() => {
    if (isAdmin) getFranchises().then(setFranchises).catch(() => setFranchises([]))
  }, [isAdmin])

  // Deep link from other admin pages (e.g. Billing's "Edit studio") — open
  // the Edit modal for a specific studio via ?edit=<id>, then strip the
  // param so Cancel/Save/refresh don't reopen it.
  useEffect(() => {
    const editId = searchParams.get('edit')
    if (!editId || studios.length === 0) return
    const match = studios.find((s) => s.id === editId)
    if (match) setEditing({ ...EMPTY, ...match })
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('edit')
      return next
    }, { replace: true })
  }, [studios, searchParams, setSearchParams])

  // Pricing tier price book — GET /api/admin/pricing-tiers
  // is admin-only server-side, so only fetch it (and only offer the
  // dropdown) for an admin, same gating as the franchise select above.
  useEffect(() => {
    if (isAdmin) listPricingTiers().then(setPricingTiers).catch(() => setPricingTiers([]))
  }, [isAdmin])

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      // monthly_price is no longer editable here (Stripe Studio Billing)
      // — the server ignores it now; drop it so a stale value in
      // `editing` state can't be silently sent and silently no-op.
      const payload = { ...editing }
      delete payload.monthly_price
      if (editing.id) await updateStudio(editing.id, payload)
      else await createStudio(payload)
      await reload()
      setEditing(null)
      // Brief "Studio saved" confirmation — additive only, doesn't
      // change the existing close-on-success timing above.
      setSavedBanner(true)
      clearTimeout(savedBannerTimeout.current)
      savedBannerTimeout.current = setTimeout(() => setSavedBanner(false), 2000)
    } catch (err) {
      setError(getApiErrorMessage(err, 'Failed to save studio'))
    } finally {
      setSaving(false)
    }
  }

  // Reactivating is low-risk — one click. Deactivating a studio cuts off its
  // staff, so it goes through the type-the-name confirm modal below.
  async function reactivate(studio) {
    await updateStudio(studio.id, { is_active: true }).catch(() => {})
    reload()
  }

  async function confirmDeactivate() {
    if (!pendingDeactivate) return
    setDeactivating(true)
    try {
      await updateStudio(pendingDeactivate.id, { is_active: false })
      setPendingDeactivate(null)
      reload()
    } catch {
      // leave the modal open so the failure is visible and retryable
    } finally {
      setDeactivating(false)
    }
  }

  const filtered = studios.filter((s) =>
    [s.name, s.display_name, s.contact_name]
      .some((v) => v && v.toLowerCase().includes(search.toLowerCase()))
  )

  const field = (label, key, type = 'text') => (
    <label className="block text-sm font-medium text-gray-700">
      {label}
      <input
        type={type}
        value={editing?.[key] ?? ''}
        onChange={(e) => setEditing((cur) => ({ ...cur, [key]: e.target.value }))}
        data-testid={`studio-${key.replace(/_/g, '-')}-input`}
        className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
      />
    </label>
  )

  return (
    <AppShell>
      <PageHeader title="Studios" subtitle="Create and manage the studios in your franchise" />
      <div className="max-w-2xl space-y-2 px-4 py-4 sm:px-8" data-testid="studios-page">
        <Button testId="studio-new-button" onClick={() => setEditing({ ...EMPTY })}>+ New studio</Button>
        {savedBanner && (
          <p className="text-sm font-medium text-green-600" data-testid="studio-saved-indicator">Studio saved</p>
        )}

        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search studios..."
          data-testid="studios-search-input"
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        {isAdmin && (
          <select
            value={franchiseFilter}
            onChange={(e) => changeFranchiseFilter(e.target.value)}
            data-testid="studios-franchise-filter"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="">All franchises</option>
            {franchises.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        )}

        <label className="flex items-center gap-2 py-1 text-sm text-gray-600">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
            data-testid="studios-show-inactive-toggle"
            className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          Show inactive
        </label>

        {filtered.map((s) => (
          <div key={s.id} data-testid="studio-row"
            className={`rounded-lg border px-4 py-3 ${s.is_active ? 'border-gray-200 bg-white' : 'border-gray-100 bg-gray-50 opacity-70'}`}>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-2">
              <div
                data-testid="studio-browse-link"
                role={isAdmin ? 'button' : undefined}
                tabIndex={isAdmin ? 0 : undefined}
                onClick={isAdmin ? () => selectStudio(s) : undefined}
                className={`flex min-w-0 flex-1 items-center gap-2 ${isAdmin ? 'cursor-pointer' : ''}`}
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-gray-900">{s.display_name || s.name}</p>
                  {s.contact_name && (
                    <p className="text-xs text-gray-500">
                      {s.contact_name}{s.contact_email ? ` · ${s.contact_email}` : ''}{s.contact_phone ? ` · ${s.contact_phone}` : ''}
                    </p>
                  )}
                  {isAdmin && (s.short_name || s.onboard_code) && (
                    <p className="text-xs text-gray-400" data-testid="studio-onboard-code">
                      Studio code: <span className="font-mono font-medium text-gray-600">{s.short_name || s.onboard_code}</span>
                    </p>
                  )}
                </div>
                {isAdmin && <IconChevronRight size={18} className="shrink-0 text-gray-300" />}
              </div>
              <div className="flex flex-wrap gap-2 sm:shrink-0">
                {isAdmin && s.is_active && (
                  <Button size="sm" testId="studio-select-button" onClick={() => selectStudio(s)}>Select</Button>
                )}
                <Button size="sm" variant="secondary" testId="studio-codes-button" onClick={() => setCodesStudio(s)}>Onboarding</Button>
                <Button size="sm" variant="secondary" testId="studio-edit-button" onClick={() => setEditing({ ...EMPTY, ...s })}>Edit</Button>
                <Button size="sm" variant={s.is_active ? 'danger' : 'secondary'} testId="studio-toggle-button"
                  onClick={() => (s.is_active ? setPendingDeactivate(s) : reactivate(s))}>
                  {s.is_active ? 'Deactivate' : 'Reactivate'}
                </Button>
              </div>
            </div>
          </div>
        ))}
        {studios.length === 0 && <p className="text-sm text-gray-500">No studios yet — create the first one.</p>}
        {studios.length > 0 && filtered.length === 0 && (
          <p className="text-sm text-gray-500">No studios match &ldquo;{search}&rdquo;.</p>
        )}
      </div>

      <Modal isOpen={!!editing} onClose={() => setEditing(null)} title={editing?.id ? 'Edit studio' : 'New studio'}>
        <div className="flex max-h-[60vh] flex-col gap-3 overflow-y-auto">
          {error && <p className="text-sm text-red-600">{error}</p>}
          {field('Studio name *', 'name')}
          {field('Display name', 'display_name')}
          {isAdmin && (
            <label className="block text-sm font-medium text-gray-700">
              Franchise
              <select
                value={editing?.franchise_id ?? ''}
                onChange={(e) => setEditing((cur) => ({ ...cur, franchise_id: e.target.value || null }))}
                data-testid="studio-franchise-select"
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="">— No franchise —</option>
                {franchises.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
              </select>
            </label>
          )}
          {isAdmin && (
            <label className="block text-sm font-medium text-gray-700">
              Pricing tier
              <select
                value={editing?.pricing_tier_id ?? ''}
                onChange={(e) => setEditing((cur) => ({ ...cur, pricing_tier_id: e.target.value || null }))}
                data-testid="studio-pricing-tier-select"
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="">No tier assigned</option>
                {pricingTiers.map((t) => (
                  <option key={t.id} value={t.id}>{formatTierOptionLabel(t)}</option>
                ))}
              </select>
            </label>
          )}
          {field('Contact name', 'contact_name')}
          {field('Contact email', 'contact_email', 'email')}
          {field('Contact phone', 'contact_phone', 'tel')}
          {field('Address line 1', 'address_line1')}
          {field('Address line 2', 'address_line2')}
          <div className="grid grid-cols-2 gap-2">
            {field('City', 'city')}
            {field('State', 'state')}
          </div>
          <div className="grid grid-cols-2 gap-2">
            {field('Postal code', 'postal_code')}
            {field('Country', 'country')}
          </div>
          {/* Monthly price moved to Manage -> Billing (Stripe Studio Billing) —
              no longer editable from the generic studio form, which closed a
              hole where a franchise manager could overwrite an
              admin-contracted price. */}
          <label className="block text-sm font-medium text-gray-700">
            Local time zone
            <select
              value={editing?.timezone ?? 'America/New_York'}
              onChange={(e) => setEditing((cur) => ({ ...cur, timezone: e.target.value }))}
              data-testid="studio-timezone-select"
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            >
              {TIMEZONES.map((z) => <option key={z} value={z}>{z}</option>)}
            </select>
          </label>
          {editing?.id && <StudioPeopleInline studioId={editing.id} />}
        </div>
        <div className="mt-4 flex justify-end gap-3">
          <Button variant="secondary" testId="studio-cancel-button" onClick={() => setEditing(null)}>Cancel</Button>
          <Button testId="studio-save-button" loading={saving} disabled={!editing?.name?.trim()} onClick={handleSave}>Save</Button>
        </div>
      </Modal>

      <StudioCodesModal studio={codesStudio} onClose={() => setCodesStudio(null)} />

      <ConfirmDeactivateModal
        open={!!pendingDeactivate}
        onClose={() => setPendingDeactivate(null)}
        onConfirm={confirmDeactivate}
        busy={deactivating}
        title="Deactivate studio"
        confirmWord={pendingDeactivate?.display_name || pendingDeactivate?.name || ''}
        confirmLabel="Deactivate studio"
      >
        <p className="font-semibold">This deactivates the studio.</p>
        <p className="mt-1">
          “{pendingDeactivate?.display_name || pendingDeactivate?.name}” will be hidden from
          active lists and its instructors and managers lose access. Its record is
          kept — you can reactivate it later from “Show inactive.”
        </p>
      </ConfirmDeactivateModal>
    </AppShell>
  )
}
