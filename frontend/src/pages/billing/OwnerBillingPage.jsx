import { useEffect, useState } from 'react'
import AppShell from '../../components/layout/AppShell'
import PageHeader from '../../components/layout/PageHeader'
import Button from '../../components/ui/Button'
import { useAuth } from '../../context/AuthContext'
import { listMyBillingStudios, createMyCheckout, createMyBillingPortalSession } from '../../api/ownerBilling'
import { APP_NAME } from '../../config/brand'

function formatPeriodEnd(value) {
  if (!value) return null
  try {
    return new Date(value).toLocaleDateString()
  } catch {
    return null
  }
}

// Opens a URL in a new tab; if that's blocked, falls back to copying it,
// and if THAT'S blocked too, hands the caller the raw URL to render as a
// link instead of losing it behind a silent failure (the exact bug fixed
// in BillingPage.jsx's admin equivalent — same fix applied here from the
// start rather than rediscovering it).
async function openOrFallback(url, { onCopied, onFallback }) {
  let opened = null
  try {
    opened = window.open(url, '_blank', 'noopener')
  } catch {
    opened = null
  }
  if (opened) return
  try {
    await navigator.clipboard?.writeText(url)
    onCopied()
  } catch {
    onFallback(url)
  }
}

// One studio's billing card: the green/red dot, its status, and whatever
// action (if any) that red state calls for.
function BillingStudioCard({ row, onChanged }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [copied, setCopied] = useState(false)
  const [fallbackUrl, setFallbackUrl] = useState(null)

  const isActive = row.status === 'active'
  const periodEnd = formatPeriodEnd(row.current_period_end)

  async function runAction(createSession) {
    setError(null)
    setFallbackUrl(null)
    setBusy(true)
    let url
    try {
      ;({ checkout_url: url } = await createSession(row.studio_id))
    } catch (err) {
      setError(err.response?.data?.detail?.message || 'Something went wrong — try again')
      setBusy(false)
      return
    }
    setBusy(false)
    await openOrFallback(url, {
      onCopied: () => { setCopied(true); setTimeout(() => setCopied(false), 1500) },
      onFallback: setFallbackUrl,
    })
    onChanged?.()
  }

  let action = null
  let instructions = null

  if (isActive) {
    // Make it explicit this isn't a one-time charge — the owner should know
    // they'll be billed automatically every period, not just that "it's
    // active."
    instructions = periodEnd
      ? `Auto-billing is enabled. Next payment on ${periodEnd}.`
      : 'Auto-billing is enabled for your subscription.'
    // Cancellation (and updating the card) happens in Stripe's own hosted
    // Billing Portal — when they cancel there, Stripe fires
    // customer.subscription.deleted, the webhook flips this to canceled, and
    // they get the notification email.
    action = (
      <Button size="sm" variant="secondary" testId="owner-billing-manage-button" loading={busy}
        onClick={() => runAction(createMyBillingPortalSession)}>
        Manage or cancel
      </Button>
    )
  } else if (row.status === 'past_due') {
    instructions = "There's a problem with your payment method."
    action = (
      <Button size="sm" testId="owner-billing-fix-payment-button" loading={busy}
        onClick={() => runAction(createMyBillingPortalSession)}>
        Fix payment method
      </Button>
    )
  } else if (row.status === 'canceled') {
    instructions = 'Your subscription has been canceled.'
    action = (
      <Button size="sm" testId="owner-billing-resubscribe-button" loading={busy}
        onClick={() => runAction(createMyCheckout)}>
        Resubscribe
      </Button>
    )
  } else if (row.checkout_ready) {
    // 'not_started' or 'incomplete', but a price has been set — self-serve.
    instructions = "Billing hasn't been set up yet."
    action = (
      <Button size="sm" testId="owner-billing-setup-button" loading={busy}
        onClick={() => runAction(createMyCheckout)}>
        Set up billing
      </Button>
    )
  } else {
    instructions = "Billing hasn't been set up yet. Contact us to get started."
  }

  return (
    <div data-testid="owner-billing-studio-card" className="rounded-xl border border-gray-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span
              data-testid="owner-billing-status-dot"
              data-status={isActive ? 'green' : 'red'}
              className={`h-2.5 w-2.5 shrink-0 rounded-full ${isActive ? 'bg-green-500' : 'bg-red-500'}`}
            />
            <p className="truncate text-sm font-semibold text-gray-900">{row.studio_name}</p>
          </div>
          <p className="mt-1 text-sm text-gray-600" data-testid="owner-billing-instructions">{instructions}</p>
          {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
          {fallbackUrl && (
            <p className="mt-1 text-xs text-gray-600">
              Couldn&apos;t open or copy automatically —{' '}
              <a href={fallbackUrl} target="_blank" rel="noopener noreferrer"
                className="text-blue-600 underline" data-testid="owner-billing-link-fallback">
                open this link
              </a>
            </p>
          )}
        </div>
        <div className="shrink-0">
          {copied ? <span className="text-xs font-medium text-green-600">Link copied!</span> : action}
        </div>
      </div>
    </div>
  )
}

// Self-serve owner Billing tab — separate from
// the admin's central roster at /setup/billing. A studio owner or franchise
// owner (owner-level only) sees their own studio(s)' subscription status
// here and can act on it themselves; an admin still has to contract the
// price first (see BillingStudioCard above), matching "admin must retain
// the ability to trigger billing until subscription is implemented."
export default function OwnerBillingPage() {
  const { myRoles } = useAuth()
  const [rows, setRows] = useState(null)
  const [loadError, setLoadError] = useState(false)

  const canSelfServe = (myRoles?.studio_owner || myRoles?.franchise_owner_level) && myRoles?.base_role !== 'admin'

  function load() {
    setRows(null)
    setLoadError(false)
    listMyBillingStudios()
      .then(setRows)
      .catch(() => { setRows([]); setLoadError(true) })
  }

  useEffect(() => {
    if (canSelfServe) load()
  }, [canSelfServe])

  if (!canSelfServe) {
    return (
      <AppShell>
        <PageHeader title="Billing" subtitle={`Your studio's subscription with ${APP_NAME}.`} />
        <div className="mx-auto max-w-lg px-4 py-4 sm:px-8" data-testid="owner-billing-page">
          <p className="text-sm text-gray-500" data-testid="owner-billing-no-access">
            You don&apos;t manage billing for any studio.
          </p>
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell>
      <PageHeader title="Billing" subtitle={`Your studio's subscription with ${APP_NAME}.`} />
      <div className="mx-auto max-w-lg space-y-3 px-4 py-4 sm:px-8" data-testid="owner-billing-page">
        {rows === null && <p className="text-sm text-gray-500">Loading…</p>}
        {loadError && <p className="text-sm text-red-600">Could not load your billing status.</p>}
        {rows !== null && rows.length === 0 && !loadError && (
          <p className="text-sm text-gray-500" data-testid="owner-billing-empty">No studios found.</p>
        )}
        {rows?.map((row) => (
          <BillingStudioCard key={row.studio_id} row={row} onChanged={load} />
        ))}
      </div>
    </AppShell>
  )
}
