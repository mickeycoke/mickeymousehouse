import client from './client'

// Notes the signed-in user hasn't disregarded since the admin last edited them.
export async function getActiveNotes() {
  const { data } = await client.get('/notes/active')
  return data.items ?? []
}

// Every active note, newest first, each flagged with whether this user has
// already disregarded it — the Notes tab's history view.
export async function getNotesHistory() {
  const { data } = await client.get('/notes/history')
  return data.items ?? []
}

export async function dismissNote(noteId) {
  const { data } = await client.post(`/notes/${noteId}/dismiss`)
  return data
}

// ── admin panel ──
export async function getAllNotes() {
  const { data } = await client.get('/admin/notes')
  return data.items ?? []
}

export async function createNote({ body, isActive = true, attachmentIds = [] }) {
  const { data } = await client.post('/admin/notes',
    { body, is_active: isActive, attachment_ids: attachmentIds })
  return data
}

export async function updateNote(noteId, { body, isActive, attachmentIds = [] }) {
  const { data } = await client.patch(`/admin/notes/${noteId}`,
    { body, is_active: isActive, attachment_ids: attachmentIds })
  return data
}

export async function deleteNote(noteId) {
  const { data } = await client.delete(`/admin/notes/${noteId}`)
  return data
}
