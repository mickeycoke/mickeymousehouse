import { useEffect, useState } from 'react'
import AppShell from '../components/layout/AppShell'
import PageHeader from '../components/layout/PageHeader'
import Button from '../components/ui/Button'
import StudioCodesModal from '../components/ownership/StudioCodesModal'
import { useAuth } from '../context/AuthContext'
import { getStudios } from '../api/ownership'

// A discoverable nav destination for studio owners/managers to find their
// instructor-onboarding and shared front-desk device links, without digging
// through Profile. Same data + same modal as ProfilePage's "Instructor
// onboarding & shared device" card (ProfilePage.jsx keeps that card as-is —
// this page is an additional, more visible entry point, not a replacement).
export default function StudioManagerPage() {
  const { myRoles } = useAuth()
  const [myStudios, setMyStudios] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [codesStudio, setCodesStudio] = useState(null)

  // The sidebar nav link already hides this page from non-managers, but that
  // alone mattered less when the page was read-only. Now it carries real
  // mutating controls (cloud backup connect/disconnect/retention), so the
  // page itself must not render them for a visitor who slips past the nav
  // gate (e.g. a direct URL hit). Mirrors ProfilePage.jsx's managesStudios.
  const managesStudios = (myRoles?.studio_owner || myRoles?.studio_manager) && myRoles?.base_role !== 'admin'

  useEffect(() => {
    if (!managesStudios) { setLoading(false); return }
    let cancelled = false
    setLoading(true)
    setLoadError(false)
    getStudios()
      .then((studios) => { if (!cancelled) setMyStudios(studios) })
      .catch(() => { if (!cancelled) { setMyStudios([]); setLoadError(true) } })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [managesStudios])

  if (!managesStudios) {
    return (
      <AppShell>
        <PageHeader title="Studio Manager" subtitle="Onboard new instructors and set up the shared front-desk device for your studio." />
        <div className="mx-auto max-w-lg px-4 py-4 sm:px-8" data-testid="studio-manager-page">
          <p className="text-sm text-gray-500" data-testid="studio-manager-no-access">
            You don&apos;t manage any studios.
          </p>
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell>
      <PageHeader
        title="Studio Manager"
        subtitle="Onboard new instructors and set up the shared front-desk device for your studio."
      />
      <div className="mx-auto max-w-lg space-y-6 px-4 py-4 sm:px-8" data-testid="studio-manager-page">
        <section className="rounded-xl border border-gray-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-gray-900">Instructor onboarding & shared device</h2>
          <p className="mt-1 text-sm text-gray-500">QR codes and links to onboard instructors and set up the front-desk tablet.</p>
          <div className="mt-3 space-y-2">
            {loading && (
              <p className="text-sm text-gray-400" data-testid="studio-manager-loading">Loading…</p>
            )}
            {!loading && loadError && (
              <p className="text-sm text-red-600" data-testid="studio-manager-load-error">
                Couldn&apos;t load your studios. Try refreshing the page.
              </p>
            )}
            {!loading && !loadError && myStudios.map((s) => (
              <div key={s.id} className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 px-3 py-2">
                <span className="truncate text-sm text-gray-800">{s.display_name || s.name}</span>
                <Button size="sm" variant="secondary" testId="studio-manager-codes-button" onClick={() => setCodesStudio(s)}>Show codes</Button>
              </div>
            ))}
            {!loading && !loadError && myStudios.length === 0 && (
              <p className="text-sm text-gray-400" data-testid="studio-manager-empty">No studios found.</p>
            )}
          </div>
        </section>
      </div>

      <StudioCodesModal studio={codesStudio} onClose={() => setCodesStudio(null)} />
    </AppShell>
  )
}
