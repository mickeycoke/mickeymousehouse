import client from './client'

// Open a new question thread with the admin.
export async function askQuestion(body, attachmentIds = []) {
  const { data } = await client.post('/questions', { body, attachment_ids: attachmentIds })
  return data
}

// My own threads, including the admin's replies.
export async function getMyQuestions() {
  const { data } = await client.get('/questions/mine')
  return data.items ?? []
}

// Append to a thread — the asker on their own, an admin on any.
export async function replyToQuestion(questionId, body, attachmentIds = []) {
  const { data } = await client.post(`/questions/${questionId}/messages`,
    { body, attachment_ids: attachmentIds })
  return data
}

// ── admin inbox ──
export async function getAllQuestions({ status } = {}) {
  const { data } = await client.get('/admin/questions', {
    params: status ? { status } : {},
  })
  return data.items ?? []
}

export async function setQuestionStatus(questionId, status) {
  const { data } = await client.patch(`/admin/questions/${questionId}`, { status })
  return data
}
