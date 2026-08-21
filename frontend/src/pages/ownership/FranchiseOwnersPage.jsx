import { useEffect, useState } from 'react'
import AppShell from '../../components/layout/AppShell'
import OwnershipPageShell from '../../components/ownership/OwnershipPageShell'
import OwnerAssignment from '../../components/ownership/OwnerAssignment'
import { OwnershipLoading, OwnershipError, OwnershipEmpty } from '../../components/ownership/OwnershipStates'
import { useFranchises } from '../../hooks/useFranchises'
import { useFranchiseOwnership } from '../../hooks/useFranchiseOwnership'
import { getOwnerCandidates } from '../../api/ownership'
import { sendInvite } from '../../api/auth'
import { getApiErrorMessage } from '../../utils/apiError'

function FranchisesPanel({ franchises, selectedId, onSelect }) {
  const sortedFranchises = [...franchises].sort((a, b) => {
    if (a.is_active !== b.is_active) return a.is_active ? -1 : 1
    return a.name.localeCompare(b.name)
  })

  if (sortedFranchises.length === 0) {
    return <OwnershipEmpty message="No franchises found." />
  }
  return (
    <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white overflow-hidden">
      {sortedFranchises.map((franchise) => (
        <li key={franchise.id}>
          <button
            data-testid={`franchise-owner-list-item-${franchise.id}`}
            onClick={() => onSelect(franchise)}
            className={
              'w-full text-left px-4 py-3 text-sm transition-colors ' +
              (selectedId === franchise.id
                ? 'bg-blue-50 text-blue-700 font-medium'
                : 'text-gray-700 hover:bg-gray-50')
            }
          >
            {franchise.name}
            {!franchise.is_active && (
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

function OwnersPanel({ franchise }) {
  const {
    franchiseOwners,
    loading,
    error,
    assignFranchiseOwner,
    removeFranchiseOwner,
  } = useFranchiseOwnership({ franchiseId: franchise.id })

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
      await assignFranchiseOwner({ ...payload, franchise_id: franchise.id })
    } catch (err) {
      setAssignError(getApiErrorMessage(err, 'Failed to assign owner'))
      throw err
    }
  }

  async function handleRemove(id) {
    try {
      await removeFranchiseOwner(id)
    } catch {
      // ignore
    }
  }

  // Fires the Phase 0 invite email for an already-assigned owner (Phase 3).
  // Errors/success messaging are handled inside OwnerAssignment per-row.
  async function handleInvite(userId) {
    return sendInvite(userId)
  }

  return (
    <div data-testid="franchise-owners-panel">
      <h2 className="text-base font-semibold text-gray-900 mb-4">{franchise.name} — Owners</h2>
      {assignError && <p className="text-sm text-red-600 mb-3">{assignError}</p>}
      <OwnerAssignment
        title="Assign franchise owner"
        ownerCandidates={candidates}
        assignments={franchiseOwners}
        ownerLabel={(u) => u.name ? `${u.name} (${u.email})` : (u.email || u.id)}
        assignmentLabel={(a) => a.user_name ? `${a.user_name} (${a.user_email})` : (a.user_email || a.user_id)}
        onAssign={handleAssign}
        onRemove={handleRemove}
        onInvite={handleInvite}
      />
    </div>
  )
}

export default function FranchiseOwnersPage() {
  const { franchises, loading, error, refetch } = useFranchises({ includeInactive: true })
  const [selectedFranchise, setSelectedFranchise] = useState(null)

  return (
    <AppShell>
      <OwnershipPageShell
        title="Franchise Owners"
        subtitle="Assign and remove owners for franchises"
      >
        <div data-testid="franchise-owners-page" className="grid grid-cols-1 gap-6 md:grid-cols-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500 mb-2">Franchises</p>
            {loading && <OwnershipLoading />}
            {!loading && error && <OwnershipError message={error} onRetry={refetch} />}
            {!loading && !error && (
              <FranchisesPanel
                franchises={franchises}
                selectedId={selectedFranchise?.id}
                onSelect={setSelectedFranchise}
              />
            )}
          </div>

          <div className="md:col-span-2">
            {selectedFranchise ? (
              <OwnersPanel franchise={selectedFranchise} />
            ) : (
              <div className="flex items-center justify-center h-32 rounded-lg border border-dashed border-gray-300 text-sm text-gray-400">
                Select a franchise to manage its owners.
              </div>
            )}
          </div>
        </div>
      </OwnershipPageShell>
    </AppShell>
  )
}
