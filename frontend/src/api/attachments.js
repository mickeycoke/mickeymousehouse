import client from './client'

// Upload one image (screenshot, pasted QR code, …). Returns {id, filename,
// content_type, size_bytes}; pass the id in attachment_ids when creating the
// note/message to link it.
export async function uploadAttachment(file) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await client.post('/attachments', form, {
    headers: { 'Content-Type': undefined },  // let the browser set the multipart boundary
  })
  return data
}

// Images are auth-gated, so a bare <img src> can't load them — fetch the bytes
// with the token and hand back an object URL (see AuthImage).
export async function fetchAttachmentUrl(attachmentId) {
  const { data } = await client.get(`/attachments/${attachmentId}`, { responseType: 'blob' })
  return URL.createObjectURL(data)
}

// Discard a draft (uploader) or strip a picture from a note (admin).
export async function deleteAttachment(attachmentId) {
  const { data } = await client.delete(`/attachments/${attachmentId}`)
  return data
}
