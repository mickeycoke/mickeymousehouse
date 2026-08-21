import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { IconBuildingCommunity, IconX } from '@tabler/icons-react'
import AppShell from '../../components/layout/AppShell'
import SetupPageShell from '../../components/setup/SetupPageShell'
import Button from '../../components/ui/Button'
import {
  getBillingConfig,
  listBillingStudios,
  setContractedAmount,
  createBillingCheckout,
} from '../../api/studioBilling'
import { getFranchises } from '../../api/ownership'

const STATUS_STYLES = {
  active: 'bg-green-100 text-green-800',
  past_due: 'bg-yellow-100 text-yellow-800',
  canceled: 'bg-red-100 text-red-800',
  incomplete: 'bg-yellow-100 text-yellow-800',
  not_started: 'bg-gray-100 text-gray-600',
}

const STATUS_LABELS = {
  active: 'Active',
  past_due: 'Past due',
  canceled: 'Canceled',
  incomplete: 'Incomplete',
  not_started: 'Not started',
}

function StatusBadge({ status }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLES[status] || STATUS_STYLES.not_started}`}>
      {STATUS_LABELS[status] || status}
    </span>
  )
}

function formatDollarsInput(cents) {
  if (cents == null) return ''
  return (cents / 100).toFixed(2)
}

function formatDollars(cents) {
  if (cents == null) return null
  const d = cents / 100
  return Number.isInteger(d) ? `$${d}` : `$${d.toFixed(2)}`
}

// Build a CSV of the billing roster from the already-loaded rows — one row
// per studio, the columns the admin sees. RFC-4180 quoting so studio names
// with commas survive.
function buildBillingCsv(rows) {
  const dollars = (cents) => (cents == null ? '' : (cents / 100).toFixed(2))
  const esc = (v) => {
    const s = v == null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const headers = [
    'Studio', 'Monthly price (USD)', 'Status', 'Next payment', 'Tier', 'Tier price (USD)',
  ]
  const lines = rows.map((r) => [
    r.studio_name,
    dollars(r.contracted_amount_cents),
    r.status,
    r.current_period_end ? new Date(r.current_period_end).toLocaleDateString() : '',
    r.tier_name || '',
    dollars(r.tier_amount_cents),
  ].map(esc).join(','))
  return [headers.join(','), ...lines].join('\n')
}

function downloadCsv(filename, csv) {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function formatPeriodEnd(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleDateString()
  } catch {
    return '—'
  }
}

// One row of the billing roster: an editable contracted price, status badge,
// next payment date, and a Send Checkout Link button. Self-contained so a
// save/checkout only re-renders and re-fetches this one row's parent state.
function BillingStudioRow({ row, onAmountSaved }) {
  const [amount, setAmount] = useState(formatDollarsInput(row.contracted_amount_cents))
  const [saving, setSaving] = useState(false)
  const [applyingTier, setApplyingTier] = useState(false)
  const [checkingOut, setCheckingOut] = useState(false)
  const [error, setError] = useState(null)
  const [sentTo, setSentTo] = useState(null)     // email the checkout link went to
  const [linkUrl, setLinkUrl] = useState(null)   // the raw Stripe link, kept below the button

  useEffect(() => {
    setAmount(formatDollarsInput(row.contracted_amount_cents))
  }, [row.contracted_amount_cents])

  async function saveAmountCents(cents, setBusy) {
    setError(null)
    setBusy(true)
    try {
      const updated = await setContractedAmount(row.studio_id, cents, row.currency || 'usd')
      onAmountSaved(updated)
    } catch {
      setError('Could not save this price')
    } finally {
      setBusy(false)
    }
  }

  async function handleSave() {
    const dollars = Number(amount)
    // $0 is allowed on purpose ("I reserve the right to have a $0 cost
    // studio") — only empty or negative is rejected.
    if (String(amount).trim() === '' || Number.isNaN(dollars) || dollars < 0) {
      setError('Enter $0 or more')
      return
    }
    await saveAmountCents(Math.round(dollars * 100), setSaving)
  }

  // One click sets the billing rate TO the tier's amount.
  async function handleApplyTier() {
    if (row.tier_amount_cents == null) return
    await saveAmountCents(row.tier_amount_cents, setApplyingTier)
  }

  async function handleCheckout() {
    setError(null)
    setSentTo(null)
    setLinkUrl(null)
    setCheckingOut(true)
    try {
      const { checkout_url: checkoutUrl, emailed_to: emailedTo } = await createBillingCheckout(row.studio_id)
      // The button's job is to EMAIL the studio their link; the raw URL is
      // kept below for the admin to grab if they want. No auto-open.
      setSentTo(emailedTo || false)   // false = created but studio had no contact email
      setLinkUrl(checkoutUrl)
    } catch (err) {
      setError(err.response?.data?.detail?.message || 'Could not create a checkout link')
    } finally {
      setCheckingOut(false)
    }
  }

  const hasPrice = row.contracted_amount_cents != null && row.contracted_amount_cents > 0
  const tierAmount = formatDollars(row.tier_amount_cents)

  return (
    <tr data-testid="billing-studio-row" data-studio-id={row.studio_id}>
      <td className="px-4 py-3 text-sm font-medium text-gray-900">
        {row.studio_name}
        <Link
          to={`/studios?edit=${row.studio_id}`}
          data-testid="billing-edit-studio-link"
          className="mt-0.5 block text-xs font-normal text-blue-600 underline"
        >
          Edit studio
        </Link>
      </td>
      <td className="px-4 py-3 align-top">
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-lg border border-gray-300 focus-within:ring-2 focus-within:ring-blue-500">
            <span className="pl-2.5 text-sm text-gray-400">$</span>
            <input
              type="number"
              min="0"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              data-testid="billing-amount-input"
              className="w-24 border-0 bg-transparent px-1.5 py-1.5 text-sm tabular-nums focus:outline-none focus:ring-0"
            />
          </div>
          <Button size="sm" variant="secondary" testId="billing-save-amount-button" loading={saving} disabled={saving} onClick={handleSave}>
            Save
          </Button>
        </div>
        {row.tier_name && (
          <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs" data-testid="billing-tier-row">
            <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2 py-0.5 font-medium text-indigo-700 ring-1 ring-inset ring-indigo-100">
              {row.tier_name}{tierAmount ? ` · ${tierAmount}/mo` : ' · custom'}
            </span>
            {row.tier_amount_cents != null && row.tier_amount_cents !== row.contracted_amount_cents && (
              <button type="button" data-testid="billing-apply-tier-button" disabled={applyingTier}
                onClick={handleApplyTier}
                className="font-medium text-blue-600 hover:underline disabled:opacity-50">
                {applyingTier ? 'Applying…' : `Apply ${tierAmount}`}
              </button>
            )}
          </div>
        )}
        {error && <p className="mt-1.5 text-xs text-red-600">{error}</p>}
      </td>
      <td className="px-4 py-3 align-top"><StatusBadge status={row.status} /></td>
      <td className="px-4 py-3 align-top text-sm tabular-nums text-gray-700">{formatPeriodEnd(row.current_period_end)}</td>
      <td className="px-4 py-3 align-top">
        <Button
          size="sm"
          variant="primary"
          testId="billing-checkout-button"
          loading={checkingOut}
          disabled={!hasPrice || checkingOut}
          onClick={handleCheckout}
        >
          Send Checkout Link
        </Button>
        {sentTo && (
          <p className="mt-1.5 flex items-center gap-1 text-xs font-medium text-emerald-700" data-testid="billing-checkout-emailed">
            <span aria-hidden="true">✓</span> Emailed to {sentTo}
          </p>
        )}
        {sentTo === false && (
          <p className="mt-1.5 text-xs text-amber-700" data-testid="billing-checkout-no-email">
            Link created — no contact email on file, copy it below.
          </p>
        )}
        {linkUrl && (
          <a
            href={linkUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-1 inline-block text-xs text-blue-600 underline"
            data-testid="billing-checkout-link-fallback"
          >
            Stripe checkout link
          </a>
        )}
      </td>
    </tr>
  )
}

// Admin-only Stripe Studio Billing — platform revenue, separate from
// Client Payments. Dormant behind GET /api/admin/billing/config the same way
// Client Payments gates its Buy UI (see ClientPackageBalanceInline.jsx).
export default function BillingPage() {
  const [enabled, setEnabled] = useState(null) // null = loading
  const [studios, setStudios] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')

  // Manage-by-franchise. The selection
  // lives in the URL (?franchise=<id>) so a reload keeps it — 'All
  // franchises' is simply the param's absence, no separate empty-state to track.
  const [searchParams, setSearchParams] = useSearchParams()
  const franchiseId = searchParams.get('franchise') || ''
  const [franchises, setFranchises] = useState([])

  function handleFranchiseChange(nextId) {
    const next = new URLSearchParams(searchParams)
    if (nextId) next.set('franchise', nextId); else next.delete('franchise')
    setSearchParams(next)
  }

  // The franchise directory for the selector — app-wide reference data, not
  // billing data, so it loads independent of the billing on/off gate below.
  useEffect(() => {
    let cancelled = false
    getFranchises()
      .then((rows) => { if (!cancelled) setFranchises(rows) })
      .catch(() => { /* selector just shows "All franchises" only */ })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    getBillingConfig()
      .then((cfg) => { if (!cancelled) setEnabled(!!cfg?.enabled) })
      .catch(() => { if (!cancelled) setEnabled(false) })
    return () => { cancelled = true }
  }, [])

  // Re-fetches whenever the franchise scope changes, so picking a franchise
  // filters the roster without a manual reload.
  useEffect(() => {
    if (enabled !== true) return
    let cancelled = false
    setLoading(true)
    listBillingStudios(franchiseId)
      .then((rows) => { if (!cancelled) setStudios(rows) })
      .catch(() => { if (!cancelled) setError('Could not load studios') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [enabled, franchiseId])

  function handleAmountSaved(updated) {
    setStudios((rows) => rows.map((r) => (r.studio_id === updated.studio_id ? updated : r)))
  }

  function handleExportCsv() {
    // Export what's on screen (respects the search filter); all studios when
    // no search is active. Date stamped so repeated exports don't collide.
    const stamp = new Date().toISOString().slice(0, 10)
    downloadCsv(`billing-${stamp}.csv`, buildBillingCsv(visibleStudios))
  }

  const term = search.trim().toLowerCase()
  const visibleStudios = term
    ? studios.filter((r) => (r.studio_name || '').toLowerCase().includes(term))
    : studios

  // Total monthly revenue = the contracted rate of EVERY studio ("total of
  // all not just active"), not only those currently billing. Active count
  // is kept as a secondary stat for context.
  const mrrCents = studios.reduce((sum, r) => sum + (r.contracted_amount_cents || 0), 0)
  const activeStudios = studios.filter((r) => r.status === 'active')
  // A price decision has been made when the amount is set — INCLUDING a
  // deliberate $0. Free studios are counted separately.
  const pricedStudios = studios.filter((r) => r.contracted_amount_cents != null)
  const freeStudios = studios.filter((r) => r.contracted_amount_cents === 0)
  const fmtUSD = (cents) => (cents / 100).toLocaleString('en-US', { style: 'currency', currency: 'USD' })

  const selectedFranchise = franchiseId ? franchises.find((f) => f.id === franchiseId) : null

  return (
    <AppShell>
      <SetupPageShell
        title={
          <span className="flex flex-wrap items-center gap-3">
            <span>Billing</span>
            {/* Selected-franchise scope pill — mirrors ContextBar's operating-
                studio pill (rounded-full blue chip + icon + a clear button) so
                "which tenant am I looking at" reads the same way everywhere. */}
            {selectedFranchise && (
              <span className="flex min-w-0 items-center" data-testid="billing-franchise-scope">
                <span className="inline-flex min-w-0 items-center gap-1.5 rounded-l-full bg-blue-600 py-1 pl-2.5 pr-2 text-xs font-semibold text-white">
                  <IconBuildingCommunity size={13} className="shrink-0" />
                  <span className="max-w-[14rem] truncate">{selectedFranchise.name}</span>
                </span>
                <button
                  type="button"
                  data-testid="billing-franchise-scope-clear"
                  onClick={() => handleFranchiseChange('')}
                  aria-label="Clear franchise filter"
                  className="rounded-r-full bg-blue-600 py-1 pl-0.5 pr-2 text-blue-100 hover:bg-blue-700 hover:text-white"
                >
                  <IconX size={13} />
                </button>
              </span>
            )}
          </span>
        }
        subtitle="Studio subscriptions — the platform's own revenue."
        actions={
          <label className="flex items-center gap-2 text-sm font-medium text-gray-600">
            Franchise
            <select
              value={franchiseId}
              data-testid="billing-franchise-select"
              onChange={(e) => handleFranchiseChange(e.target.value)}
              className="rounded-lg border border-gray-300 bg-white py-1.5 pl-2 pr-7 text-sm font-medium text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All franchises</option>
              {franchises.map((f) => (
                <option key={f.id} value={f.id}>{f.name}</option>
              ))}
            </select>
          </label>
        }
      >
        <div data-testid="billing-page">
          {enabled === null && (
            <p className="text-sm text-gray-500">Loading…</p>
          )}

          {enabled === false && (
            <p className="text-sm text-gray-500" data-testid="billing-disabled-message">
              Billing isn&apos;t configured yet. Set the Stripe keys and turn on billing to send studios a checkout link.
            </p>
          )}

          {enabled === true && (
            <>
              {error && <p className="mb-4 text-sm text-red-600">{error}</p>}
              {loading && <p className="text-sm text-gray-500">Loading studios…</p>}
              {!loading && (
                <>
                  <div
                    data-testid="billing-revenue-summary"
                    className="mb-4 flex flex-wrap items-end gap-x-8 gap-y-2 rounded-xl border border-gray-200 bg-gradient-to-br from-emerald-50 to-white px-5 py-4"
                  >
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700/70">Total monthly revenue</p>
                      <p className="text-3xl font-semibold tabular-nums text-gray-900" data-testid="billing-mrr">{fmtUSD(mrrCents)}</p>
                    </div>
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Annualized</p>
                      <p className="text-lg font-medium tabular-nums text-gray-700">{fmtUSD(mrrCents * 12)}</p>
                    </div>
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Studios priced</p>
                      <p className="text-lg font-medium tabular-nums text-gray-700">{pricedStudios.length}<span className="text-sm text-gray-400"> / {studios.length}</span></p>
                    </div>
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Free ($0)</p>
                      <p className="text-lg font-medium tabular-nums text-gray-700" data-testid="billing-free-count">{freeStudios.length}</p>
                    </div>
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Active now</p>
                      <p className="text-lg font-medium tabular-nums text-gray-700">{activeStudios.length}</p>
                    </div>
                  </div>
                  <div className="mb-3 flex items-center gap-2">
                    <input
                      type="text"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Search studios…"
                      data-testid="billing-search-input"
                      className="w-full max-w-sm rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <Button
                      size="sm"
                      variant="secondary"
                      testId="billing-export-csv-button"
                      onClick={handleExportCsv}
                      disabled={studios.length === 0}
                    >
                      Export CSV
                    </Button>
                  </div>
                  <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Studio</th>
                          <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Contracted price</th>
                          <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Status</th>
                          <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Next payment</th>
                          <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">Checkout</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {studios.length === 0 && (
                          <tr>
                            <td colSpan={5} className="px-4 py-6 text-center text-sm text-gray-500">No studios found.</td>
                          </tr>
                        )}
                        {studios.length > 0 && visibleStudios.length === 0 && (
                          <tr>
                            <td colSpan={5} className="px-4 py-6 text-center text-sm text-gray-500">No studios match &ldquo;{search}&rdquo;.</td>
                          </tr>
                        )}
                        {visibleStudios.map((row) => (
                          <BillingStudioRow key={row.studio_id} row={row} onAmountSaved={handleAmountSaved} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </SetupPageShell>
    </AppShell>
  )
}
