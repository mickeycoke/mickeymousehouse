import { useState } from 'react'
import AppShell from '../../components/layout/AppShell'
import OwnershipPageShell from '../../components/ownership/OwnershipPageShell'
import OwnershipRelationshipTable from '../../components/ownership/OwnershipRelationshipTable'
import { OwnershipLoading, OwnershipError, OwnershipEmpty } from '../../components/ownership/OwnershipStates'
import Button from '../../components/ui/Button'
import { useFranchises } from '../../hooks/useFranchises'
import { useFranchiseStudios } from '../../hooks/useFranchiseStudios'
import { useVisibleStudios } from '../../hooks/useOwnershipScope'
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
            data-testid={`franchise-studios-list-item-${franchise.id}`}
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

function StudiosPanel({ franchise }) {
  const { studios: allStudios } = useVisibleStudios({ includeInactive: false })
  const { franchiseStudios: allFranchiseStudios } = useFranchiseStudios({ includeInactive: false })
  const {
    franchiseStudios,
    loading,
    error,
    assignFranchiseStudio,
    removeFranchiseStudio,
  } = useFranchiseStudios({ franchiseId: franchise.id })

  const [selectedStudioId, setSelectedStudioId] = useState('')
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState(null)

  const linkedStudioIds = new Set(franchiseStudios.map((fs) => fs.studio_id))
  const globallyLinkedStudioIds = new Set(allFranchiseStudios.map((fs) => fs.studio_id))
  const availableStudios = allStudios.filter((s) => (
    !linkedStudioIds.has(s.id) && !globallyLinkedStudioIds.has(s.id)
  ))

  async function handleAdd() {
    if (!selectedStudioId) return
    setAdding(true)
    setAddError(null)
    try {
      await assignFranchiseStudio({ franchise_id: franchise.id, studio_id: selectedStudioId })
      setSelectedStudioId('')
    } catch (err) {
      setAddError(getApiErrorMessage(err, 'Failed to add studio'))
    } finally {
      setAdding(false)
    }
  }

  async function handleRemove(linkId) {
    try {
      await removeFranchiseStudio(linkId)
    } catch {
      // ignore
    }
  }

  const columns = [
    { key: 'studio_name', label: 'Studio', render: (row) => row.studio_name || row.studio_id },
    {
      key: 'actions',
      label: 'Actions',
      render: (row) => (
        <Button
          variant="ghost"
          size="sm"
          testId={`franchise-studio-remove-${row.id}`}
          onClick={() => handleRemove(row.id)}
        >
          Remove
        </Button>
      ),
    },
  ]

  if (loading) return <OwnershipLoading />
  if (error) return <OwnershipError message={error} />

  return (
    <div data-testid="franchise-studios-panel">
      <h2 className="text-base font-semibold text-gray-900 mb-4">{franchise.name} — Studios</h2>

      {/* Add studio */}
      <div className="mb-5 flex gap-3 items-end">
        <label className="flex-1 text-sm font-medium text-gray-700">
          Add studio
          <select
            data-testid="franchise-studios-add-select"
            value={selectedStudioId}
            onChange={(e) => setSelectedStudioId(e.target.value)}
            disabled={adding || availableStudios.length === 0}
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50"
          >
            <option value="">
              {availableStudios.length === 0 ? 'All studios already added' : 'Select studio…'}
            </option>
            {availableStudios.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </label>
        <Button
          testId="franchise-studios-add-button"
          onClick={handleAdd}
          loading={adding}
          disabled={!selectedStudioId || adding}
        >
          Add
        </Button>
      </div>
      {addError && <p className="text-sm text-red-600 mb-3">{addError}</p>}

      {/* Linked studios */}
      <OwnershipRelationshipTable
        columns={columns}
        rows={franchiseStudios}
        loading={false}
        error={null}
        emptyMessage="No studios linked to this franchise yet."
      />
    </div>
  )
}

export default function FranchiseStudiosPage() {
  const { franchises, loading, error, refetch } = useFranchises({ includeInactive: true })
  const [selectedFranchise, setSelectedFranchise] = useState(null)

  return (
    <AppShell>
      <OwnershipPageShell
        title="Franchise Studios"
        subtitle="Connect studios to franchise ownership groups"
      >
        <div data-testid="franchise-studios-page" className="grid grid-cols-1 gap-6 md:grid-cols-3">
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
              <StudiosPanel franchise={selectedFranchise} />
            ) : (
              <div className="flex items-center justify-center h-32 rounded-lg border border-dashed border-gray-300 text-sm text-gray-400">
                Select a franchise to manage its studios.
              </div>
            )}
          </div>
        </div>
      </OwnershipPageShell>
    </AppShell>
  )
}
