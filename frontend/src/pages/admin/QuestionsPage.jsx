import { useCallback, useEffect, useState } from 'react'
import AppShell from '../../components/layout/AppShell'
import PageHeader from '../../components/layout/PageHeader'
import Badge from '../../components/ui/Badge'
import Button from '../../components/ui/Button'
import { ts } from '../../utils/time'
import { getAllQuestions, replyToQuestion, setQuestionStatus } from '../../api/questions'
import { useAttachmentDrafts } from '../../components/attachments/useAttachmentDrafts'
import { AddImageButton, DraftStrip } from '../../components/attachments/DraftStrip'
import { AttachmentList } from '../../components/attachments/AuthImage'
import { renderWithLinks } from '../../utils/linkify'

// Admin inbox for "Ask a question": every thread, who sent it, when, and the
// reply box that closes the loop back to the user's Notes page.
const STATUS_COLOR = { new: 'red', read: 'blue', resolved: 'green' }

// Filter pills, in the order they appear. 'all' is the only one with no
// server-side status param — everything else maps 1:1 to a real status.
const FILTER_PILLS = [
  { value: 'new', label: 'New', activeClass: 'bg-red-600 text-white' },
  { value: 'read', label: 'Read', activeClass: 'bg-blue-600 text-white' },
  { value: 'resolved', label: 'Resolved', activeClass: 'bg-green-600 text-white' },
  { value: 'all', label: 'All', activeClass: 'bg-gray-700 text-white' },
]

export default function QuestionsPage() {
  const [threads, setThreads] = useState(null)
  // Defaults to "new" — the inbox should open on what
  // still needs attention, not the full history.
  const [statusFilter, setStatusFilter] = useState('new')
  const [replyFor, setReplyFor] = useState(null)
  const [replyDraft, setReplyDraft] = useState('')
  const replyImages = useAttachmentDrafts()

  const load = useCallback(() => {
    setThreads(null)
    getAllQuestions({ status: statusFilter === 'all' ? undefined : statusFilter })
      .then(setThreads)
      .catch(() => setThreads([]))
  }, [statusFilter])

  useEffect(() => { load() }, [load])

  const fmt = (iso) =>
    iso ? ts(iso).toLocaleString(undefined, {
      weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
    }) : '—'

  async function sendReply(id) {
    const body = replyDraft.trim()
    if (!body && !replyImages.readyIds.length) return
    try {
      await replyToQuestion(id, body, replyImages.readyIds)
      setReplyDraft(''); replyImages.clearDrafts(); setReplyFor(null); load()
    } catch { /* keep the draft */ }
  }

  async function mark(id, status) {
    try { await setQuestionStatus(id, status); load() } catch { /* ignore */ }
  }

  const items = threads ?? []

  return (
    <AppShell>
      <PageHeader
        title="Questions"
        subtitle="Questions from instructors and studio owners — reply and they'll see it on their Notes page"
      />
      <div className="max-w-3xl px-4 py-4 sm:px-8" data-testid="questions-page">
        <div className="mb-3 flex flex-wrap gap-2" data-testid="questions-status-filter">
          {FILTER_PILLS.map((pill) => (
            <button
              key={pill.value}
              type="button"
              onClick={() => setStatusFilter(pill.value)}
              data-testid={`questions-filter-${pill.value}`}
              aria-pressed={statusFilter === pill.value}
              className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                statusFilter === pill.value
                  ? pill.activeClass
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {pill.label}
            </button>
          ))}
        </div>

        {threads === null && (
          <p data-loading="true" className="text-sm text-gray-400 animate-pulse">Loading questions…</p>
        )}
        {threads !== null && items.length === 0 && (
          <p data-testid="questions-empty" className="text-sm text-gray-500">No questions yet.</p>
        )}

        <div className="space-y-3">
          {items.map((t) => (
            <div key={t.id} data-testid="question-thread" className="rounded-xl border border-gray-200 bg-white p-4">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <span className="block truncate text-sm font-medium text-gray-900">
                    {t.user_name || 'Unknown user'}
                  </span>
                  <span className="block truncate text-xs text-gray-500">
                    {[t.user_email, t.studio_name].filter(Boolean).join(' · ') || '—'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge color={STATUS_COLOR[t.status] || 'gray'}>{t.status}</Badge>
                  <span className="text-xs text-gray-400">{fmt(t.created_at)}</span>
                </div>
              </div>

              <div className="space-y-2">
                {t.messages.map((m) => (
                  <div
                    key={m.id}
                    className={`rounded-lg px-3 py-2 text-sm ${
                      m.is_admin_reply ? 'bg-blue-50 text-gray-800' : 'bg-gray-50 text-gray-700'
                    }`}
                  >
                    {m.body && <p className="whitespace-pre-wrap">{renderWithLinks(m.body)}</p>}
                    <AttachmentList attachments={m.attachments} />
                    <p className="mt-1 text-[11px] text-gray-400">
                      {m.is_admin_reply ? (m.author_name || 'Admin') : (t.user_name || 'User')} · {fmt(m.created_at)}
                    </p>
                  </div>
                ))}
              </div>

              {replyFor === t.id ? (
                <div className="mt-3">
                  <textarea
                    value={replyDraft}
                    onChange={(e) => setReplyDraft(e.target.value)}
                    onPaste={replyImages.onPaste}
                    rows={3}
                    data-testid="question-reply-input"
                    placeholder="Write a reply… (paste a screenshot or QR code to attach it)"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <DraftStrip drafts={replyImages.drafts} onRemove={replyImages.removeDraft} />
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <AddImageButton onFiles={replyImages.addFiles} testId="question-reply-attach" />
                    <div className="flex gap-2">
                      <Button variant="secondary" testId="question-reply-cancel"
                        onClick={() => { setReplyFor(null); setReplyDraft(''); replyImages.clearDrafts() }}>Cancel</Button>
                      <Button testId="question-reply-send"
                        disabled={(!replyDraft.trim() && !replyImages.readyIds.length) || replyImages.uploading}
                        onClick={() => sendReply(t.id)}>Send reply</Button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="mt-3 flex flex-wrap gap-3 text-xs">
                  <button type="button" data-testid="question-reply-open"
                    className="font-medium text-blue-600 hover:underline"
                    onClick={() => { setReplyFor(t.id); setReplyDraft('') }}>Reply</button>
                  {t.status !== 'read' && (
                    <button type="button" className="font-medium text-gray-600 hover:underline"
                      onClick={() => mark(t.id, 'read')}>Mark read</button>
                  )}
                  {t.status !== 'resolved' && (
                    <button type="button" className="font-medium text-green-700 hover:underline"
                      onClick={() => mark(t.id, 'resolved')}>Mark resolved</button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  )
}
