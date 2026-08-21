import { useCallback, useEffect, useState } from 'react'
import AppShell from '../components/layout/AppShell'
import PageHeader from '../components/layout/PageHeader'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import { useAuth } from '../context/AuthContext'
import { ts } from '../utils/time'
import { useNavigate } from 'react-router-dom'
import { getNotesHistory, dismissNote, getAllNotes, createNote, updateNote, deleteNote } from '../api/notes'
import { deleteAttachment } from '../api/attachments'
import { useAttachmentDrafts } from '../components/attachments/useAttachmentDrafts'
import { AddImageButton, DraftStrip } from '../components/attachments/DraftStrip'
import { AttachmentList } from '../components/attachments/AuthImage'
import { renderMarkdown } from '../utils/markdown'
import { APP_NAME } from '../config/brand'

// "Notes to Users": the announcements an admin wants staff to read. New notes
// sit up top with a prominent Disregard; disregarded ones stay below as a
// running history. The chat link lives at the top so the history has room to
// grow underneath it.
export default function NotesPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [notes, setNotes] = useState(null)
  const navigate = useNavigate()

  const loadNotes = useCallback(() => {
    getNotesHistory().then(setNotes).catch(() => setNotes([]))
  }, [])
  useEffect(() => { loadNotes() }, [loadNotes])

  const fmt = (iso) =>
    iso ? ts(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
    }) : ''

  const fresh = (notes ?? []).filter((n) => !n.dismissed)
  const previous = (notes ?? []).filter((n) => n.dismissed)

  async function handleDisregard(id) {
    // Moves the note down into "Previous notes" rather than removing it.
    // (During impersonation the server refuses to record the dismissal, so
    // the real user's view is untouched.)
    setNotes((cur) => (cur ?? []).map((n) => (n.id === id ? { ...n, dismissed: true } : n)))
    try { await dismissNote(id) } catch { loadNotes() }
  }

  return (
    <AppShell>
      <PageHeader title="Notes to users" subtitle={`Announcements from the ${APP_NAME} team`} />
      <div className="max-w-3xl px-4 py-4 sm:px-8" data-testid="notes-page">

        <div className="mb-5">
          <Button variant="secondary" testId="notes-open-chat" onClick={() => navigate('/chat')}>
            Chat with us
          </Button>
        </div>

        {notes === null && (
          <p data-loading="true" className="text-sm text-gray-400 animate-pulse">Loading notes…</p>
        )}
        {notes !== null && fresh.length === 0 && (
          <p data-testid="notes-empty" className="text-sm text-gray-500">
            No new notes right now.
          </p>
        )}

        {fresh.map((note) => (
          <div
            key={note.id}
            data-testid="note-card"
            className="mb-4 rounded-xl border border-blue-200 bg-blue-50/60 p-5"
          >
            {/* Scrollable: a broadcast note can be a full release write-up, and
                an unbounded card pushed Disregard and Ask a question off the
                screen — on a phone the actions became unreachable. The note
                scrolls inside its own box; the buttons stay put. */}
            <div
              data-testid="note-body"
              className="max-h-[55vh] overflow-y-auto pr-1 text-sm text-gray-800"
            >
              {renderMarkdown(note.body)}
            </div>
            <AttachmentList attachments={note.attachments} />
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button testId="note-disregard" onClick={() => handleDisregard(note.id)}>
                Disregard
              </Button>
              <Button variant="secondary" testId="note-ask-question"
                onClick={() => navigate('/chat')}>
                Ask a question
              </Button>
            </div>
          </div>
        ))}

        {previous.length > 0 && (
          <div className="mt-8" data-testid="notes-history">
            <h2 className="mb-3 text-sm font-semibold text-gray-900">Previous notes</h2>
            {previous.map((note) => (
              <div
                key={note.id}
                data-testid="note-previous-card"
                className="mb-3 rounded-xl border border-gray-200 bg-white p-4"
              >
                <div
                  data-testid="note-previous-body"
                  className="max-h-64 overflow-y-auto pr-1 text-sm text-gray-600"
                >
                  {renderMarkdown(note.body)}
                </div>
                <AttachmentList attachments={note.attachments} />
                <p className="mt-2 text-[11px] text-gray-400">Sent {fmt(note.created_at)}</p>
              </div>
            ))}
          </div>
        )}

        {isAdmin && <AdminNotesPanel onChanged={loadNotes} fmt={fmt} />}
      </div>
    </AppShell>
  )
}

// Admin-only: write the notes everyone sees at login.
function AdminNotesPanel({ onChanged, fmt }) {
  const [all, setAll] = useState([])
  const [body, setBody] = useState('')
  const [editingId, setEditingId] = useState(null)
  // Pictures already on the note being edited (removable one by one) — new
  // ones ride along as drafts and are linked on save.
  const [existing, setExisting] = useState([])
  const images = useAttachmentDrafts()

  const load = useCallback(() => {
    getAllNotes().then(setAll).catch(() => setAll([]))
  }, [])
  useEffect(() => { load() }, [load])

  async function save() {
    const text = body.trim()
    if (!text) return
    if (editingId) await updateNote(editingId, { body: text, isActive: true, attachmentIds: images.readyIds })
    else await createNote({ body: text, attachmentIds: images.readyIds })
    setBody(''); setEditingId(null); setExisting([]); images.clearDrafts(); load(); onChanged()
  }

  async function removeExisting(id) {
    try {
      await deleteAttachment(id)
      setExisting((cur) => cur.filter((a) => a.id !== id))
      load(); onChanged()
    } catch { /* leave it visible */ }
  }

  async function toggleActive(n) {
    await updateNote(n.id, { body: n.body, isActive: !n.is_active })
    load(); onChanged()
  }

  async function remove(id) {
    await deleteNote(id)
    load(); onChanged()
  }

  return (
    <div className="mt-10 border-t border-gray-200 pt-6" data-testid="admin-notes-panel">
      <h2 className="mb-1 text-sm font-semibold text-gray-900">Manage notes (admin)</h2>
      <p className="mb-3 text-xs text-gray-500">
        Everyone signed in sees active notes at login. Editing a note shows it again to
        people who already disregarded it. <strong>Markdown is rendered</strong> —
        paste a <code>.md</code> release note straight in.
      </p>

      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        onPaste={images.onPaste}
        rows={5}
        data-testid="admin-note-input"
        placeholder="Write a note to your users… Markdown works: # heading, **bold**, - bullets, [link](url), tables. Paste a screenshot to attach it."
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      {existing.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2" data-testid="admin-note-existing-images">
          {existing.map((a) => (
            <span key={a.id} className="flex items-center gap-1 rounded-lg border border-gray-200 bg-gray-50 px-2 py-1 text-xs text-gray-600">
              {a.filename}
              <button type="button" aria-label={`Remove ${a.filename}`}
                className="font-medium text-red-600 hover:underline"
                onClick={() => removeExisting(a.id)}>×</button>
            </span>
          ))}
        </div>
      )}
      {body.trim() && (
        <div className="mt-2 rounded-lg border border-blue-200 bg-blue-50/50 p-3" data-testid="admin-note-preview">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-blue-700">
            Preview — this is what users will see
          </p>
          <div className="max-h-64 overflow-y-auto pr-1 text-sm text-gray-800">
            {renderMarkdown(body)}
          </div>
        </div>
      )}
      <DraftStrip drafts={images.drafts} onRemove={images.removeDraft} />
      <div className="mt-2 flex items-center justify-between gap-2">
        <AddImageButton onFiles={images.addFiles} testId="admin-note-attach" />
        <div className="flex gap-2">
          {editingId && (
            <Button variant="secondary" testId="admin-note-cancel"
              onClick={() => { setEditingId(null); setBody(''); setExisting([]); images.clearDrafts() }}>Cancel</Button>
          )}
          <Button testId="admin-note-save" disabled={!body.trim() || images.uploading} onClick={save}>
            {editingId ? 'Save changes' : 'Post note'}
          </Button>
        </div>
      </div>

      <div className="mt-5 space-y-2">
        {all.map((n) => (
          <div key={n.id} data-testid="admin-note-row" className="rounded-lg border border-gray-200 bg-white p-3">
            <div className="mb-1 flex items-center justify-between gap-2">
              <Badge color={n.is_active ? 'green' : 'gray'}>{n.is_active ? 'active' : 'hidden'}</Badge>
              <span className="text-[11px] text-gray-400">updated {fmt(n.updated_at)}</span>
            </div>
            <div className="max-h-40 overflow-y-auto pr-1 text-xs text-gray-700">
              {renderMarkdown(n.body)}
            </div>
            {n.attachments?.length > 0 && (
              <p className="mt-1 text-[11px] text-gray-400">
                {n.attachments.length} image{n.attachments.length > 1 ? 's' : ''} attached
              </p>
            )}
            <div className="mt-2 flex gap-3 text-xs">
              <button type="button" className="font-medium text-blue-600 hover:underline"
                onClick={() => { setEditingId(n.id); setBody(n.body); setExisting(n.attachments ?? []); images.clearDrafts() }}>Edit</button>
              <button type="button" className="font-medium text-gray-600 hover:underline"
                onClick={() => toggleActive(n)}>{n.is_active ? 'Hide' : 'Show'}</button>
              <button type="button" className="font-medium text-red-600 hover:underline"
                onClick={() => remove(n.id)}>Delete</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
