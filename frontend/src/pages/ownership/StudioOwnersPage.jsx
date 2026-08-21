import { useEffect, useState } from 'react'
import AppShell from '../../components/layout/AppShell'
import OwnershipPageShell from '../../components/ownership/OwnershipPageShell'
import OwnerAssignment from '../../components/ownership/OwnerAssignment'
import { OwnershipLoading, OwnershipError, OwnershipEmpty } from '../../components/ownership/OwnershipStates'
import { useVisibleStudios } from '../../hooks/useOwnershipScope'
import { useStudioOwnership } from '../../hooks/useStudioOwnership'
import { getOwnerCandidates } from '../../api/ownership'
import { sendInvite } from '../../api/auth'
import { getApiErrorMessage } from '../../utils/apiError'

function StudiosPanel({ studios, selectedId, onSelect }) {
  if (studios.length === 0) {
    return <OwnershipEmpty message="No studios available." />
  }
  return (
    <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white overflow-hidden">
      {studios.map((studio) => (
        <li key={studio.id}>
          <button
            data-testid={`studio-list-item-${studio.id}`}
            onClick={() => onSelect(studio)}
            className={
              'w-full text-left px-4 py-3 text-sm transition-colors ' +
              (selectedId === studio.id
                ? 'bg-blue-50 text-blue-700 font-medium'
                : 'text-gray-700 hover:bg-gray-50')
            }
          >
            {studio.name}
            {!studio.is_active && (
              <span className="ml-2 inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
                Inactive
              </span>
            )}
          </button>
        </li>
      ))}
    </ul>
  )
}

function OwnersPanel({ studio, studioId }) {
  const {
    studioOwners,
    loading,
    error,
    assignStudioOwner,
    removeStudioOwner,
  } = useStudioOwnership({ studioId })

  const [candidates, setCandidates] = useState([])
  const [assignError, setAssignError] = useState(null)

  useEffect(() => {
    getOwnerCandidates()
      .then(setCandidates)
      .catch(() => {})
  }, [])

  if (loading) return <OwnershipLoading />
  if (error) return <OwnershipError message={error} />

  async function handleAssign(payload) {
    setAssignError(null)
    try {
      await assignStudioOwner({ ...payload, studio_id: studioId })
    } catch (err) {
      setAssignError(getApiErrorMessage(err, 'Failed to assign owner'))
      throw err
    }
  }

  async function handleRemove(id) {
    try {
      await removeStudioOwner(id)
    } catch {
      // ignore — list will refresh
    }
  }

  // Fires the Phase 0 invite email for an already-assigned owner (Phase 2).
  // Errors/success messaging are handled inside OwnerAssignment per-row.
  async function handleInvite(userId) {
    return sendInvite(userId)
  }

  return (
    <div data-testid="studio-owners-panel">
      <h2 className="text-base font-semibold text-gray-900 mb-4">{studio.name} — Owners</h2>
      {assignError && <p className="text-sm text-red-600 mb-3">{assignError}</p>}
      <OwnerAssignment
        title="Assign studio owner"
        ownerCandidates={candidates}
        assignments={studioOwners}
        ownerLabel={(u) => u.name ? `${u.name} (${u.email})` : (u.email || u.id)}
        assignmentLabel={(a) => a.user_name ? `${a.user_name} (${a.user_email})` : (a.user_email || a.user_id)}
        onAssign={handleAssign}
        onRemove={handleRemove}
        onInvite={handleInvite}
      />
    </div>
  )
}

export default function StudioOwnersPage() {
  const { studios, loading, error, refetch } = useVisibleStudios({ includeInactive: false })
  const [selectedStudio, setSelectedStudio] = useState(null)

  return (
    <AppShell>
      <OwnershipPageShell
        title="Studio Owners"
        subtitle="Assign and remove owners for individual studios"
      >
        <div data-testid="studio-owners-page" className="grid grid-cols-1 gap-6 md:grid-cols-3">
          {/* Left: studio list */}
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500 mb-2">Studios</p>
            {loading && <OwnershipLoading />}
            {!loading && error && <OwnershipError message={error} onRetry={refetch} />}
            {!loading && !error && (
              <StudiosPanel
                studios={studios}
                selectedId={selectedStudio?.id}
                onSelect={setSelectedStudio}
              />
            )}
          </div>

          {/* Right: owners for selected studio */}
          <div className="md:col-span-2">
            {selectedStudio ? (
              <OwnersPanel studio={selectedStudio} studioId={selectedStudio.id} />
            ) : (
              <div className="flex items-center justify-center h-32 rounded-lg border border-dashed border-gray-300 text-sm text-gray-400">
                Select a studio to manage its owners.
              </div>
            )}
          </div>
        </div>
      </OwnershipPageShell>
    </AppShell>
  )
}
