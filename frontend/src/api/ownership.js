import client from './client'

function inactiveParams(includeInactive) {
  return includeInactive ? { include_inactive: true } : {}
}

export async function getOwnershipScope() {
  const { data } = await client.get('/ownership/scope')
  return data
}

export async function getOwnerCandidates({ q } = {}) {
  const { data } = await client.get('/ownership/owner-candidates', {
    params: q ? { q } : {},
  })
  return data
}

// allStudios: admins only — bypass the operating-studio scope so the studio
// switcher can list every studio. Every other caller leaves it off, so its
// dropdown auto-scopes to the selected operating studio.
export async function getStudios({ includeInactive = false, franchiseId = null, allStudios = false } = {}) {
  const { data } = await client.get('/studios', {
    params: {
      ...inactiveParams(includeInactive),
      ...(franchiseId ? { franchise_id: franchiseId } : {}),
      ...(allStudios ? { all_studios: true } : {}),
    },
  })
  return data
}

export async function getStudio(id) {
  const { data } = await client.get(`/studios/${id}`)
  return data
}

export async function getFranchises({ includeInactive = false } = {}) {
  const { data } = await client.get('/franchises', {
    params: inactiveParams(includeInactive),
  })
  return data
}

export async function getFranchise(id) {
  const { data } = await client.get(`/franchises/${id}`)
  return data
}

export async function createFranchise(payload) {
  const { data } = await client.post('/franchises', payload)
  return data
}

export async function updateFranchise(id, payload) {
  const { data } = await client.put(`/franchises/${id}`, payload)
  return data
}

export async function deactivateFranchise(id) {
  const { data } = await client.delete(`/franchises/${id}`)
  return data
}

export async function getStudioOwners({ studioId, userId, includeInactive = false } = {}) {
  const { data } = await client.get('/studio-owners', {
    params: {
      ...(studioId ? { studio_id: studioId } : {}),
      ...(userId ? { user_id: userId } : {}),
      ...inactiveParams(includeInactive),
    },
  })
  return data
}

export async function assignStudioOwner(payload) {
  const { data } = await client.post('/studio-owners', payload)
  return data
}

export async function updateStudioOwner(id, payload) {
  const { data } = await client.put(`/studio-owners/${id}`, payload)
  return data
}

export async function removeStudioOwner(id) {
  const { data } = await client.delete(`/studio-owners/${id}`)
  return data
}

export async function getFranchiseOwners({ franchiseId, userId, includeInactive = false } = {}) {
  const { data } = await client.get('/franchise-owners', {
    params: {
      ...(franchiseId ? { franchise_id: franchiseId } : {}),
      ...(userId ? { user_id: userId } : {}),
      ...inactiveParams(includeInactive),
    },
  })
  return data
}

export async function assignFranchiseOwner(payload) {
  const { data } = await client.post('/franchise-owners', payload)
  return data
}

export async function updateFranchiseOwner(id, payload) {
  const { data } = await client.put(`/franchise-owners/${id}`, payload)
  return data
}

export async function removeFranchiseOwner(id) {
  const { data } = await client.delete(`/franchise-owners/${id}`)
  return data
}

export async function getFranchiseStudios({ franchiseId, studioId, includeInactive = false } = {}) {
  const { data } = await client.get('/franchise-studios', {
    params: {
      ...(franchiseId ? { franchise_id: franchiseId } : {}),
      ...(studioId ? { studio_id: studioId } : {}),
      ...inactiveParams(includeInactive),
    },
  })
  return data
}

export async function assignFranchiseStudio(payload) {
  const { data } = await client.post('/franchise-studios', payload)
  return data
}

export async function updateFranchiseStudio(id, payload) {
  const { data } = await client.put(`/franchise-studios/${id}`, payload)
  return data
}

export async function removeFranchiseStudio(id) {
  const { data } = await client.delete(`/franchise-studios/${id}`)
  return data
}

export async function createStudio(payload) {
  const { data } = await client.post('/studios', payload)
  return data
}

// Onboarding + shared-device links & QR codes for a studio (owner/manager/admin).
export async function getStudioAccessCodes(studioId) {
  const { data } = await client.get(`/studios/${studioId}/access-codes`)
  return data  // { studio_code, onboard: {url, qr}, shared: {url, qr} }
}

export async function updateStudio(id, payload) {
  const { data } = await client.put(`/studios/${id}`, payload)
  return data
}
