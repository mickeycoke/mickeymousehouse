import client from './client'

// Admin login log. event_type: password | shared_pin | impersonation.
export async function getLoginEvents({ eventType, success, limit = 100, offset = 0 } = {}) {
  const { data } = await client.get('/admin/login-events', {
    params: {
      ...(eventType ? { event_type: eventType } : {}),
      ...(success !== undefined && success !== '' ? { success } : {}),
      limit,
      offset,
    },
  })
  return data
}
