import { useCallback, useEffect, useState } from 'react'
import AppShell from '../components/layout/AppShell'
import PageHeader from '../components/layout/PageHeader'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import { ts } from '../utils/time'
import { askQuestion, getMyQuestions, replyToQuestion } from '../api/questions'
import { useAttachmentDrafts } from '../components/attachments/useAttachmentDrafts'
import { AddImageButton, DraftStrip } from '../components/attachments/DraftStrip'
import { AttachmentList } from '../components/attachments/AuthImage'
import { renderWithLinks } from '../utils/linkify'
import { APP_NAME } from '../config/brand'

// The user's own private conversation with the team. Threads are private to
// whoever opened them — only the asker and an admin can see one, so this
// reads like a direct chat rather than a shared board. (The broadcast
// announcements live on the Notes page; this is the reply channel.)
export default function ChatPage() {
  const [threads, setThreads] = useState(null)
  const [draft, setDraft] = useState('')
  const [replyFor, setReplyFor] = useState(null)
  const [replyDraft, setReplyDraft] = useState('')
  const newImages = useAttachmentDrafts()
  const replyImages = useAttachmentDrafts()

  const load = useCallback(() => {
    getMyQuestions().then(setThreads).catch(() => setThreads([]))
  }, [])
  useEffect(() => { load() }, [load])

  const fmt = (iso) =>
    iso ? ts(iso).toLocaleString(undefined, {
      weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
    }) : ''

  async function send() {
    const body = draft.trim()
    if (!body && !newImages.readyIds.length) return
    try {
      await askQuestion(body, newImages.readyIds)
      setDraft(''); newImages.clearDrafts(); load()
    } catch { /* keep draft */ }
  }

  async function sendReply(id) {
    const body = replyDraft.trim()
    if (!body && !replyImages.readyIds.length) return
    try {
      await replyToQuestion(id, body, replyImages.readyIds)
      setReplyDraft(''); replyImages.clearDrafts(); setReplyFor(null); load()
    } catch { /* keep draft */ }
  }

  const items = threads ?? []

  return (
    <AppShell>
      <PageHeader
        title="Chat with us"
        subtitle={`Ask the ${APP_NAME} team anything — missing features, problems, questions`}
      />
      <div className="max-w-3xl px-4 py-4 sm:px-8" data-testid="chat-page">

        {/* Start a new conversation */}
        <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold text-gray-900">Send a message</h2>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onPaste={newImages.onPaste}
            rows={4}
            data-testid="chat-input"
            placeholder="What's on your mind? Paste a screenshot right here if it helps."
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <DraftStrip drafts={newImages.drafts} onRemove={newImages.removeDraft} />
          <div className="mt-3 flex items-center justify-between">
            <AddImageButton onFiles={newImages.addFiles} testId="chat-attach" />
            <Button testId="chat-send"
              disabled={(!draft.trim() && !newImages.readyIds.length) || newImages.uploading}
              onClick={send}>Send</Button>
          </div>
          <p className="mt-2 text-xs text-gray-500">
            Only you and the {APP_NAME} team can see your messages.
          </p>
        </div>

        {threads === null && (
          <p data-loading="true" className="text-sm text-gray-400 animate-pulse">Loading…</p>
        )}
        {threads !== null && items.length === 0 && (
          <p data-testid="chat-empty" className="text-sm text-gray-500">
            No messages yet — send one above and we’ll reply here.
          </p>
        )}

        <div className="space-y-3">
          {items.map((t) => (
            <div key={t.id} data-testid="chat-thread" className="rounded-xl border border-gray-200 bg-white p-4">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="text-xs text-gray-500">Started {fmt(t.created_at)}</span>
                <Badge color={t.status === 'resolved' ? 'green' : t.status === 'read' ? 'blue' : 'gray'}>
                  {t.status}
                </Badge>
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
                      {m.is_admin_reply ? `${APP_NAME} team` : 'You'} · {fmt(m.created_at)}
                    </p>
                  </div>
                ))}
              </div>
              {replyFor === t.id ? (
                <div className="mt-2">
                  <textarea
                    value={replyDraft}
                    onChange={(e) => setReplyDraft(e.target.value)}
                    onPaste={replyImages.onPaste}
                    rows={3}
                    data-testid="chat-reply-input"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  />
                  <DraftStrip drafts={replyImages.drafts} onRemove={replyImages.removeDraft} />
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <AddImageButton onFiles={replyImages.addFiles} testId="chat-reply-attach" />
                    <div className="flex gap-2">
                      <Button variant="secondary" testId="chat-reply-cancel"
                        onClick={() => { setReplyFor(null); setReplyDraft(''); replyImages.clearDrafts() }}>Cancel</Button>
                      <Button testId="chat-reply-send"
                        disabled={(!replyDraft.trim() && !replyImages.readyIds.length) || replyImages.uploading}
                        onClick={() => sendReply(t.id)}>Send</Button>
                    </div>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  data-testid="chat-reply-open"
                  onClick={() => { setReplyFor(t.id); setReplyDraft('') }}
                  className="mt-2 text-xs font-medium text-blue-600 hover:underline"
                >
                  Reply
                </button>
              )}
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  )
}
