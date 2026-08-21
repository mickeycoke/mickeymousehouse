import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import AppShell from '../../components/layout/AppShell'
import FranchiseForm from '../../components/ownership/FranchiseForm'
import OwnershipPageShell from '../../components/ownership/OwnershipPageShell'
import { OwnershipError, OwnershipLoading } from '../../components/ownership/OwnershipStates'
import { useFranchise, useFranchises } from '../../hooks/useFranchises'
import { getApiErrorMessage } from '../../utils/apiError'
import FranchiseOwnersInline from '../../components/ownership/FranchiseOwnersInline'

export default function FranchiseFormPage() {
  const navigate = useNavigate()
  const { franchiseId } = useParams()
  const isEdit = Boolean(franchiseId)
  const { franchise, loading, error, refetch } = useFranchise(franchiseId)
  const { createFranchise, updateFranchise, deactivateFranchise } = useFranchises({ includeInactive: true })
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)

  async function handleSubmit(payload) {
    setSaving(true)
    setSaveError(null)
    try {
      if (isEdit) {
        await updateFranchise(franchiseId, payload)
      } else {
        await createFranchise(payload)
      }
      navigate('/ownership/franchises')
    } catch (err) {
      setSaveError(getApiErrorMessage(err, 'Failed to save franchise'))
    } finally {
      setSaving(false)
    }
  }

  async function handleDeactivate() {
    setSaving(true)
    setSaveError(null)
    try {
      await deactivateFranchise(franchiseId)
      navigate('/ownership/franchises')
    } catch (err) {
      setSaveError(getApiErrorMessage(err, 'Failed to deactivate franchise'))
      setSaving(false)
    }
  }

  async function handleReactivate() {
    await handleSubmit({ is_active: true })
  }

  return (
    <AppShell>
      <OwnershipPageShell title={isEdit ? `Edit ${franchise?.name || 'Franchise'}` : 'New Franchise'}>
        {loading && <OwnershipLoading />}
        {!loading && error && <OwnershipError message={error} onRetry={refetch} />}
        {!loading && !error && (
          <div className="max-w-xl">
            <FranchiseForm
              initialValues={franchise ?? {}}
              onSubmit={handleSubmit}
              onCancel={() => navigate('/ownership/franchises')}
              onDeactivate={isEdit && franchise?.is_active ? handleDeactivate : undefined}
              onReactivate={isEdit && franchise?.is_active === false ? handleReactivate : undefined}
              saving={saving}
              error={saveError}
            />
            {franchiseId && <FranchiseOwnersInline franchiseId={franchiseId} />}
          </div>
        )}
      </OwnershipPageShell>
    </AppShell>
  )
}
