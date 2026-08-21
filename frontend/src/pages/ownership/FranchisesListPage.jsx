import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../../components/layout/AppShell'
import OwnershipPageShell from '../../components/ownership/OwnershipPageShell'
import OwnershipRelationshipTable from '../../components/ownership/OwnershipRelationshipTable'
import Button from '../../components/ui/Button'
import Badge from '../../components/ui/Badge'
import ConfirmDeactivateModal from '../../components/ui/ConfirmDeactivateModal'
import { useFranchises } from '../../hooks/useFranchises'
import { useOperatingFranchise } from '../../context/FranchiseContext'

export default function FranchisesListPage() {
  const navigate = useNavigate()
  const { setFranchise } = useOperatingFranchise()
  const [includeInactive, setIncludeInactive] = useState(false)
  const [pendingDeactivate, setPendingDeactivate] = useState(null)  // franchise row
  const [deactivating, setDeactivating] = useState(false)
  const {
    franchises,
    loading,
    error,
    deactivateFranchise,
    updateFranchise,
  } = useFranchises({ includeInactive })

  async function confirmDeactivate() {
    if (!pendingDeactivate) return
    setDeactivating(true)
    try {
      await deactivateFranchise(pendingDeactivate.id)
      setPendingDeactivate(null)
    } catch {
      // leave the modal open so the error state is obvious and retryable
    } finally {
      setDeactivating(false)
    }
  }

  const columns = [
    { key: 'name', label: 'Name' },
    { key: 'description', label: 'Description', render: (row) => row.description || '—' },
    { key: 'display_order', label: 'Order', render: (row) => row.display_order ?? '—' },
    {
      key: 'is_active',
      label: 'Status',
      render: (row) => <Badge color={row.is_active ? 'green' : 'gray'}>{row.is_active ? 'Active' : 'Inactive'}</Badge>,
    },
    {
      key: 'actions',
      label: 'Actions',
      render: (row) => (
        <div className="flex gap-2" onClick={(event) => event.stopPropagation()}>
          {row.is_active && (
            <Button
              size="sm"
              testId="franchise-select-button"
              onClick={() => {
                setFranchise({ id: row.id, name: row.name })
                navigate('/studios')
              }}
            >
              Select
            </Button>
          )}
          <Button variant="secondary" size="sm" onClick={() => navigate(`/ownership/franchises/${row.id}`)}>
            Edit
          </Button>
          {row.is_active ? (
            <Button variant="ghost" size="sm" testId="franchise-deactivate-button" onClick={() => setPendingDeactivate(row)}>
              Deactivate
            </Button>
          ) : (
            <Button variant="ghost" size="sm" onClick={() => updateFranchise(row.id, { is_active: true })}>
              Reactivate
            </Button>
          )}
        </div>
      ),
    },
  ]

  return (
    <AppShell>
      <OwnershipPageShell
        title="Franchises"
        subtitle="Create and manage franchise records"
        actions={<Button onClick={() => navigate('/ownership/franchises/new')}>+ New Franchise</Button>}
      >
        <div data-testid="franchises-list-page">
          <label className="mb-4 flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(event) => setIncludeInactive(event.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            Show inactive
          </label>
          <OwnershipRelationshipTable
            columns={columns}
            rows={franchises}
            loading={loading}
            error={error}
            emptyMessage="No franchises found."
            onRowClick={(row) => navigate(`/ownership/franchises/${row.id}`)}
          />
        </div>
      </OwnershipPageShell>

      <ConfirmDeactivateModal
        open={!!pendingDeactivate}
        onClose={() => setPendingDeactivate(null)}
        onConfirm={confirmDeactivate}
        busy={deactivating}
        title="Deactivate franchise"
        confirmWord={pendingDeactivate?.name || ''}
        confirmLabel="Deactivate franchise"
      >
        <p className="font-semibold">This shuts down the entire franchise.</p>
        <p className="mt-1">
          “{pendingDeactivate?.name}” and its franchise-wide reporting will be deactivated,
          and every studio linked to it stops rolling up to it. This affects all of the
          franchise’s studios at once — it is not something you want to do by accident.
        </p>
        <p className="mt-1">You can reactivate it later from “Show inactive.”</p>
      </ConfirmDeactivateModal>
    </AppShell>
  )
}
