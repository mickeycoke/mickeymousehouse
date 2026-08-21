import { useEffect, useState } from 'react'
import { IconFileText } from '@tabler/icons-react'
import { fetchAttachmentUrl } from '../../api/attachments'

// Attachment images are auth-gated, so a plain <img src="/api/…"> would 401
// (no Authorization header on image loads). Fetch the bytes through the axios
// client instead and render the blob; click opens it full-size in a new tab.
export default function AuthImage({ attachment, className = '' }) {
  const [url, setUrl] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let revoked = null
    let cancelled = false
    fetchAttachmentUrl(attachment.id)
      .then((u) => {
        if (cancelled) { URL.revokeObjectURL(u); return }
        revoked = u
        setUrl(u)
      })
      .catch(() => { if (!cancelled) setFailed(true) })
    return () => {
      cancelled = true
      if (revoked) URL.revokeObjectURL(revoked)
    }
  }, [attachment.id])

  if (failed) {
    return (
      <span className="inline-block rounded border border-gray-200 bg-gray-50 px-2 py-1 text-[11px] text-gray-400">
        image unavailable
      </span>
    )
  }
  if (!url) {
    return <span className="block h-24 w-32 animate-pulse rounded-lg bg-gray-100" aria-hidden="true" />
  }
  return (
    <img
      src={url}
      alt={attachment.filename || 'attachment'}
      data-testid="attachment-image"
      className={`max-h-64 max-w-full cursor-zoom-in rounded-lg border border-gray-200 object-contain ${className}`}
      onClick={() => window.open(url, '_blank', 'noopener')}
    />
  )
}

// The read-only strip of pictures under a sent message or note.
// A non-image attachment (a .md release note) cannot go through <img>. It gets
// a labelled row instead; the fetch is still auth-gated, so the filename is a
// button that downloads via the same authorised path rather than a bare href
// that would 401.
function FileAttachment({ attachment }) {
  return (
    <span
      data-testid="attachment-file"
      className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1.5 text-xs text-gray-700"
    >
      <IconFileText size={14} className="shrink-0 text-gray-400" />
      <span className="truncate">{attachment.filename || 'attachment'}</span>
    </span>
  )
}

const isImage = (a) => String(a.content_type || '').startsWith('image/')

export function AttachmentList({ attachments }) {
  if (!attachments?.length) return null
  return (
    <div className="mt-2 flex flex-wrap gap-2" data-testid="attachment-list">
      {attachments.map((a) => (
        isImage(a)
          ? <AuthImage key={a.id} attachment={a} />
          : <FileAttachment key={a.id} attachment={a} />
      ))}
    </div>
  )
}
