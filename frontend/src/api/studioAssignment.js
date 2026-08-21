import client from './client'

// Admin: the studio-less staff migration backlog and bulk assignment.
export async function getStudioBacklog() {
  const { data } = await client.get('/admin/studio-assignment/backlog')
  return data
}

export async function assignStudio({ studioId, userIds = [] }) {
  const { data } = await client.post('/admin/studio-assignment/assign', {
    studio_id: studioId,
    user_ids: userIds,
  })
  return data
}
