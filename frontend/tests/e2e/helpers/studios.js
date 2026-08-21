// Shared E2E helper: create a studio the suite can clean up after itself.
//
// Every spec that needed a studio POSTed its own with whatever name it liked
// (`StepAway Studio <ts>`, `DuoNotes <ts>`, `E2E FS Studio add <ts>`...) and
// never removed it. Dev ended up with 84 active test studios against 17 real
// ones — the studio picker was 83% junk, which is exactly what the owner
// complained about.
//
// So: ONE prefix, and a global teardown that retires anything carrying it.
// Deactivate rather than delete — `is_active = false` is the app's own
// retirement mechanism, it keeps the rows for post-mortem, and it is a single
// boolean to undo.
export const E2E_STUDIO_PREFIX = 'E2E-TEST'

/** Unique, obviously-test studio name. `label` says which spec made it. */
export function e2eStudioName(label) {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
  return `${E2E_STUDIO_PREFIX} ${label} ${suffix}`
}

/**
 * Create a studio for a test. Works with either `request` or `page.request`.
 * Throws loudly rather than returning null — a silent seed failure gets
 * reported as a skip, which reads like a pass.
 */
export async function createTestStudio(requestish, label, headers) {
  const name = e2eStudioName(label)
  const resp = await requestish.post('http://localhost:8000/api/studios', {
    headers,
    data: { name, display_name: name },
  })
  if (!resp.ok()) {
    throw new Error(`createTestStudio(${label}) failed: ${resp.status()} ${await resp.text()}`)
  }
  return resp.json()
}

/**
 * Retire every studio this suite has ever created. Called from the global
 * teardown, so it also cleans up after a run that crashed mid-spec — which is
 * how the 84 accumulated in the first place.
 */
export async function deactivateE2EStudios(request) {
  const loginRes = await request.post('http://localhost:8000/api/auth/login', {
    data: { email: 'admin@example.com', password: 'admin123' },
  })
  if (!loginRes.ok()) return { retired: 0, reason: 'login failed' }
  const { access_token } = await loginRes.json()
  const headers = { Authorization: `Bearer ${access_token}` }

  const listRes = await request.get('http://localhost:8000/api/studios', { headers })
  if (!listRes.ok()) return { retired: 0, reason: `list failed ${listRes.status()}` }
  const studios = await listRes.json()

  let retired = 0
  for (const s of Array.isArray(studios) ? studios : []) {
    if (!s.is_active) continue
    if (!String(s.name || '').startsWith(E2E_STUDIO_PREFIX)) continue
    const put = await request.put(`http://localhost:8000/api/studios/${s.id}`, {
      headers, data: { is_active: false },
    })
    if (put.ok()) retired += 1
  }
  return { retired }
}
