import client from './client'

// Admin: full role picture per user (base role + all hats)
export async function getRolesSummary() {
  const { data } = await client.get('/roles/summary')
  return data.users
}

// The current user's own hats — drives UI capabilities
export async function getMyRoles() {
  const { data } = await client.get('/roles/me')
  return data
}

// One-stop role editor (admin): base role + all hats in one call
export async function setUserRoles(userId, payload) {
  const { data } = await client.put(`/roles/user/${userId}`, payload)
  return data
}
