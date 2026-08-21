import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Button from '../ui/Button'
import { useAuth } from '../../context/AuthContext'
import { getActiveNotes, dismissNote } from '../../api/notes'
import { AttachmentList } from '../attachments/AuthImage'
import { renderMarkdown } from '../../utils/markdown'

// Shown once per signed-in identity: the admin's active notes, with a
// prominent Disregard and a way to ask staff a question.
//
// The "seen" flag is keyed by USER ID, not just the browser session. A single
// global flag meant that once an admin had seen the note, stepping into
// impersonation never re-showed it — the broadcast silently vanished for every
// impersonated user, which is exactly when an admin is checking what their
// studios actually see. Keying by id gives each identity the broadcast once.
const seenKey = (userId) => `mmh_notes_seen:${userId || 'anon'}`

export default function LoginNotesModal() {
  const { user } = useAuth()
  const userId = user?.id
  const [notes, setNotes] = useState([])
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    if (!userId) return
    if (sessionStorage.getItem(seenKey(userId))) return
    let cancelled = false
    getActiveNotes()
      .then((items) => {
        if (cancelled || !items.length) return
        setNotes(items)
        setOpen(true)
        sessionStorage.setItem(seenKey(userId), '1')
      })
      .catch(() => { /* never block the app on an announcement */ })
    return () => { cancelled = true }
  }, [userId])

  if (!open || !notes.length) return null

  async function disregard(id) {
    const remaining = notes.filter((n) => n.id !== id)
    setNotes(remaining)
    if (!remaining.length) setOpen(false)
    try { await dismissNote(id) } catch { /* it'll simply show again */ }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" aria-hidden="true" onClick={() => setOpen(false)} />
      <div
        role="dialog"
        aria-modal="true"
        data-testid="login-notes-modal"
        className="relative z-10 mx-4 max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6 shadow-xl"
      >
        <h2 className="mb-4 text-lg font-semibold text-gray-900">Notes to users</h2>

        {notes.map((note) => (
          <div key={note.id} className="mb-4 rounded-lg border border-blue-200 bg-blue-50/60 p-4">
            <div data-testid="login-note-body" className="max-h-[50vh] overflow-y-auto pr-1 text-sm text-gray-800">{renderMarkdown(note.body)}</div>
            <AttachmentList attachments={note.attachments} />
            <div className="mt-4 flex flex-col gap-2">
              <Button testId="modal-note-disregard" onClick={() => disregard(note.id)}>
                Disregard
              </Button>
              <Button
                variant="secondary"
                testId="modal-note-ask"
                onClick={() => { setOpen(false); navigate('/notes') }}
              >
                Ask a question
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
