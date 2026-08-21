import client from './client'

export async function getUsers() {
  const { data } = await client.get('/users')
  return data
}

export async function getUser(id) {
  const { data } = await client.get(`/users/${id}`)
  return data
}

export async function createUser(payload) {
  const { data } = await client.post('/users', payload)
  return data
}

export async function updateUser(id, payload) {
  const { data } = await client.put(`/users/${id}`, payload)
  return data
}

export async function deleteUser(id) {
  const { data } = await client.delete(`/users/${id}`)
  return data
}

// Shared-device PIN for an instructor (admin / studio owner-manager only).
export async function getUserPin(id) {
  const { data } = await client.get(`/users/${id}/pin`)
  return data  // { user_id, name, pin, has_pin }
}

// Set (4–8 digits) or clear (pin: null) an instructor's shared-device PIN.
export async function setUserPin(id, pin) {
  const { data } = await client.put(`/users/${id}/pin`, { pin })
  return data
}
