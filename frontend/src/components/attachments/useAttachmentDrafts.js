import { useCallback, useRef, useState } from 'react'
import { uploadAttachment, deleteAttachment } from '../../api/attachments'

// Pending pictures for one composer. Each added file shows a local preview
// immediately and uploads in the background; send passes the uploaded ids
// (attachment_ids) so the server links them to the new note/message.
export function useAttachmentDrafts() {
  const [drafts, setDrafts] = useState([])   // {key, id|null, filename, previewUrl, error}
  const keyRef = useRef(0)

  const addFiles = useCallback((fileList) => {
    const images = Array.from(fileList || []).filter((f) => f.type.startsWith('image/'))
    for (const file of images) {
      const key = ++keyRef.current
      const previewUrl = URL.createObjectURL(file)
      setDrafts((cur) => [...cur, { key, id: null, filename: file.name, previewUrl, error: false }])
      uploadAttachment(file)
        .then((a) => setDrafts((cur) => cur.map((d) => (d.key === key ? { ...d, id: a.id } : d))))
        .catch(() => setDrafts((cur) => cur.map((d) => (d.key === key ? { ...d, error: true } : d))))
    }
    return images.length > 0
  }, [])

  // Paste handler for composer textareas: a pasted screenshot becomes a draft.
  const onPaste = useCallback((e) => {
    if (addFiles(e.clipboardData?.files)) e.preventDefault()
  }, [addFiles])

  const removeDraft = useCallback((key) => {
    setDrafts((cur) => {
      const gone = cur.find((d) => d.key === key)
      if (gone) {
        URL.revokeObjectURL(gone.previewUrl)
        if (gone.id) deleteAttachment(gone.id).catch(() => { /* sweeper will get it */ })
      }
      return cur.filter((d) => d.key !== key)
    })
  }, [])

  const clearDrafts = useCallback(() => {
    setDrafts((cur) => {
      cur.forEach((d) => URL.revokeObjectURL(d.previewUrl))
      return []
    })
  }, [])

  const readyIds = drafts.filter((d) => d.id && !d.error).map((d) => d.id)
  const uploading = drafts.some((d) => !d.id && !d.error)
  return { drafts, addFiles, onPaste, removeDraft, clearDrafts, readyIds, uploading }
}
