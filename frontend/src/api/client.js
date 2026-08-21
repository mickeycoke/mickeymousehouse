import axios from 'axios'

// Follow vite's `base` so the app works when it is served under a path prefix
// as well as at the root. `base` only rewrites ASSET urls — XHR is ours to fix,
// and a hardcoded '/api' posted to the hostname root instead of the mount,
// which the reverse proxy answered with 405.
//   base '/'        -> '/api'        (normal dev, unchanged)
//   base '/mount/'   -> '/mount/api'  (served under a path mount)
const client = axios.create({
  baseURL: `${import.meta.env.BASE_URL}api`.replace(/\/{2,}/g, '/'),
  headers: { 'Content-Type': 'application/json' },
})

// Attach token — and, if an admin has selected an operating studio, the
// X-Studio-Id header that scopes the whole backend to that studio.
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  try {
    const raw = localStorage.getItem('pt-operating-studio')
    if (raw) {
      const s = JSON.parse(raw)
      if (s?.id) config.headers['X-Studio-Id'] = s.id
    }
  } catch { /* ignore */ }
  return config
})

// On 401: token is missing/expired — clear it and bounce to login
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Clear everything session-scoped — including the operating studio —
      // so nothing leaks into the next login on this device.
      ;['access_token', 'auth_user', 'admin_token', 'admin_user',
        'pt-operating-studio'].forEach((k) => localStorage.removeItem(k))
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default client
