import { useEffect, useState } from 'react'
import Modal from './Modal'
import Button from './Button'

// A deliberately high-friction confirm for destructive deactivations. Two
// independent actions are required before anything happens: the user must type
// the exact name AND click the danger button (which stays disabled until the
// typed value matches). This guards against a single accidental click taking
// down a whole franchise (and all its studios) or a studio.
export default function ConfirmDeactivateModal({
  open,
  onClose,
  onConfirm,
  title,
  confirmWord,
  confirmLabel = 'Deactivate',
  busy = false,
  children,
}) {
  const [typed, setTyped] = useState('')

  // Reset the typed guard every time the modal opens for a new target.
  useEffect(() => { if (open) setTyped('') }, [open, confirmWord])

  const matches =
    typed.trim().length > 0 &&
    typed.trim().toLowerCase() === (confirmWord || '').trim().toLowerCase()

  return (
    <Modal isOpen={open} onClose={onClose} title={title}>
      <div className="space-y-4" data-testid="confirm-deactivate-modal">
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {children}
        </div>
        <label className="block text-sm font-medium text-gray-700">
          Type <span className="font-mono font-semibold text-gray-900">{confirmWord}</span> to confirm
          <input
            type="text"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            data-testid="confirm-deactivate-input"
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-500"
          />
        </label>
        <div className="flex justify-end gap-3">
          <Button variant="secondary" testId="confirm-deactivate-cancel" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="danger"
            testId="confirm-deactivate-confirm"
            loading={busy}
            disabled={!matches}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
