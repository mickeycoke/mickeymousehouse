import { useEffect, useState } from 'react'
import Modal from '../ui/Modal'
import Button from '../ui/Button'
import { getUserPin, setUserPin } from '../../api/users'
import { getApiErrorMessage } from '../../utils/apiError'

// View + set an instructor's shared-device PIN (admin / studio owner-manager).
// The PIN is shown in the clear on purpose: it's the code the studio hands out
// so instructors can sign in on the shared front-desk tablet.
export default function InstructorPinModal({ instructor, onClose }) {
  const [loading, setLoading] = useState(false)
  const [info, setInfo] = useState(null)     // { pin, has_pin }
  const [draft, setDraft] = useState('')     // new PIN being typed
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)       // { kind: 'ok' | 'err', text }

  useEffect(() => {
    setInfo(null); setDraft(''); setMsg(null)
    if (!instructor?.id) return
    setLoading(true)
    getUserPin(instructor.id)
      .then((d) => setInfo(d))
      .catch((err) => setMsg({ kind: 'err', text: getApiErrorMessage(err, 'Could not load PIN') }))
      .finally(() => setLoading(false))
  }, [instructor?.id])

  async function save(nextPin) {
    setSaving(true); setMsg(null)
    try {
      const d = await setUserPin(instructor.id, nextPin)
      setInfo(d)
      setDraft('')
      setMsg({ kind: 'ok', text: nextPin ? 'PIN saved.' : 'PIN cleared.' })
    } catch (err) {
      setMsg({ kind: 'err', text: getApiErrorMessage(err, 'Could not save PIN') })
    } finally {
      setSaving(false)
    }
  }

  function onSubmit(e) {
    e.preventDefault()
    const v = draft.trim()
    if (!/^\d{4,8}$/.test(v)) return setMsg({ kind: 'err', text: 'PIN must be 4 to 8 digits.' })
    save(v)
  }

  const hasHiddenLegacy = info && info.has_pin && !info.pin

  return (
    <Modal isOpen={!!instructor} onClose={onClose} title={`Shared-device PIN — ${instructor?.name ?? ''}`}>
      <div className="space-y-4" data-testid="instructor-pin-modal">
        <p className="text-sm text-gray-500">
          This is the PIN {instructor?.name || 'the instructor'} enters on the studio’s shared
          front-desk tablet to sign in. Only you (studio management) and admins can see it.
        </p>

        {loading && <p className="text-sm text-gray-400">Loading…</p>}

        {info && (
          <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Current PIN</p>
            {info.pin ? (
              <p className="mt-1 font-mono text-2xl font-semibold tracking-widest text-gray-900" data-testid="instructor-pin-value">
                {info.pin}
              </p>
            ) : hasHiddenLegacy ? (
              <p className="mt-1 text-sm text-gray-600">
                A PIN is set but was imported and can’t be shown. Set a new one below to make it viewable.
              </p>
            ) : (
              <p className="mt-1 text-sm text-gray-600">No PIN set yet.</p>
            )}
          </div>
        )}

        {msg && (
          <p className={`text-sm ${msg.kind === 'ok' ? 'text-green-700' : 'text-red-600'}`} data-testid="instructor-pin-msg">
            {msg.text}
          </p>
        )}

        <form onSubmit={onSubmit} className="space-y-3">
          <label className="block text-sm font-medium text-gray-700">
            {info?.has_pin ? 'Change PIN' : 'Set PIN'} (4–8 digits)
            <input
              type="text"
              inputMode="numeric"
              autoComplete="off"
              value={draft}
              onChange={(e) => setDraft(e.target.value.replace(/\D/g, '').slice(0, 8))}
              data-testid="instructor-pin-input"
              placeholder="e.g. 1234"
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono tracking-widest focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </label>
          <div className="flex items-center justify-between gap-3">
            {info?.has_pin ? (
              <Button type="button" variant="ghost" testId="instructor-pin-clear" loading={saving}
                onClick={() => save(null)}>
                Clear PIN
              </Button>
            ) : <span />}
            <div className="flex gap-3">
              <Button type="button" variant="secondary" testId="instructor-pin-cancel" onClick={onClose}>Close</Button>
              <Button type="submit" testId="instructor-pin-save" loading={saving} disabled={!draft.trim()}>Save PIN</Button>
            </div>
          </div>
        </form>
      </div>
    </Modal>
  )
}
