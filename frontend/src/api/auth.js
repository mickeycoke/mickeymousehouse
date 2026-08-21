import client from './client'

export async function loginApi(email, password) {
  const { data } = await client.post('/auth/login', { email, password })
  return data  // { access_token, user }
}

export async function logoutApi() {
  await client.post('/auth/logout')
}

// Admin testing aid: get an access token for another user. Pass studioId to
// scope the impersonated session to one studio (so the instructor only sees
// that studio's data); the backend bakes it into the token.
export async function impersonateApi(userId, studioId = null) {
  const { data } = await client.post(`/auth/impersonate/${userId}`, {}, {
    params: studioId ? { studio_id: studioId } : undefined,
  })
  return data
}

// Phase 0 onboarding: validate a magic-link invite token before showing the
// set-password form. Invalid/expired/used tokens reject with a 400 rather
// than resolving with { valid: false } — callers should catch and treat any
// rejection the same as an invalid link.
export async function getInviteInfo(token) {
  const { data } = await client.get(`/auth/invite/${token}`)
  return data  // { valid, name, email }
}

export async function setPassword(token, password) {
  const { data } = await client.post('/auth/set-password', { token, password })
  return data  // { access_token, user }
}

// Mint a set-password link and GET IT BACK instead of emailing it — for
// handing over in person when email is down or the person has no inbox handy.
// Same authorisation as sendInvite. Resolves { link, name, email,
// expires_in_hours }.
export async function getSetupLink(userId) {
  const { data } = await client.post('/auth/setup-link', { user_id: userId })
  return data
}

// Self-service "forgot my password": request a reset link. Resolves with the
// same { sent: true } shape whether or not the email matched a user — the
// backend is deliberately silent about that, so don't branch on the result.
export async function forgotPassword(email) {
  const { data } = await client.post('/auth/forgot-password', { email })
  return data  // { sent }
}

// Validate a reset link before showing the choose-new-password form.
// Invalid/expired/used tokens reject with a 400, same contract as
// getInviteInfo above — callers should catch and treat any rejection as an
// invalid link.
export async function getResetPasswordInfo(token) {
  const { data } = await client.get(`/auth/reset-password/${token}`)
  return data  // { valid, name, email }
}

export async function resetPassword(token, password) {
  const { data } = await client.post('/auth/reset-password', { token, password })
  return data  // { access_token, user }
}

// Phase 2/3 onboarding: send (or resend) a "set up your account" magic-link
// email to an already-assigned studio/franchise owner. Requires admin or
// franchise-manager auth (enforced server-side). In dev, invite_link is
// populated so the flow is testable without an email provider.
export async function sendInvite(userId) {
  const { data } = await client.post('/auth/invite', { user_id: userId })
  return data  // { sent, email, invite_link }
}

// The signed-in user changes their own password.
export async function changePassword(currentPassword, newPassword) {
  const { data } = await client.post('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  })
  return data
}

// Phase 1b shared-device login (PUBLIC, no auth). Resolve a studio and list the
// instructors who have a PIN set (id + name only).
export async function sharedLookup(studioCode) {
  const { data } = await client.post('/auth/shared/lookup', { studio_code: studioCode })
  return data // { studio: { id, name }, instructors: [{ id, name }] }
}

// Verify name + PIN within a studio; returns a short-lived, studio-scoped
// session token (stored exactly like a normal login).
export async function sharedLogin(studioCode, userId, pin) {
  const { data } = await client.post('/auth/shared/login', {
    studio_code: studioCode,
    user_id: userId,
    pin,
  })
  return data // { access_token, user }
}
