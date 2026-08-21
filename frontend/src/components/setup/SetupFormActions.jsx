import Button from '../ui/Button'

// P2-052: Standard form action buttons for setup forms
// Props: onSave, onCancel, onDelete?, onDeactivate?, onReactivate?, saving?, isActive?
export default function SetupFormActions({
  onSave,
  onCancel,
  onDelete,
  onDeactivate,
  onReactivate,
  saving = false,
  isActive = true,
  saveTestId = 'form-save-button',
  cancelTestId = 'form-cancel-button',
  deactivateTestId = 'form-deactivate-button',
  reactivateTestId = 'form-reactivate-button',
  deleteTestId = 'form-delete-button',
}) {
  return (
    <div className="flex items-center justify-between pt-4 border-t border-gray-200">
      <div className="flex gap-3">
        <Button
          variant="primary"
          onClick={onSave}
          loading={saving}
          disabled={saving}
          testId={saveTestId}
        >
          Save
        </Button>
        <Button
          variant="secondary"
          onClick={onCancel}
          disabled={saving}
          testId={cancelTestId}
        >
          Cancel
        </Button>
      </div>

      <div className="flex gap-3">
        {onDeactivate && isActive && (
          <Button
            variant="ghost"
            onClick={onDeactivate}
            disabled={saving}
            testId={deactivateTestId}
          >
            Deactivate
          </Button>
        )}
        {onReactivate && !isActive && (
          <Button
            variant="ghost"
            onClick={onReactivate}
            disabled={saving}
            testId={reactivateTestId}
          >
            Reactivate
          </Button>
        )}
        {onDelete && (
          <Button
            variant="danger"
            onClick={onDelete}
            disabled={saving}
            testId={deleteTestId}
          >
            Delete
          </Button>
        )}
      </div>
    </div>
  )
}
