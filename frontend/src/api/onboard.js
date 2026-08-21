import client from './client'

// Phase 1a self-serve onboarding (PUBLIC, no auth). Resolve a studio by its
// onboard code and list its unclaimed instructors (id + name).
export async function studioLookup(studioCode) {
  const { data } = await client.post('/onboard/studio-lookup', { studio_code: studioCode })
  return data // { studio: { id, name }, instructors: [{ id, name }] }
}

// Confirms the picked name is really you before the flow asks for an email —
// 3 wrong PINs from one IP locks that IP out of onboarding for an hour
// (backend-enforced; this call just surfaces the same limit early).
// needs_setup: true when this account has no real email on
// file (placeholder/none) -> the combined email+password setup form; false ->
// a real email already exists, point them at Forgot Password instead.
export async function verifyPin(userId, pin) {
  const { data } = await client.post('/onboard/verify-pin', { user_id: userId, pin })
  return data // { ok, needs_setup }
}

// Instructor claims their own record. Two modes:
//   password omitted -> legacy magic-link invite; in dev (console email
//     backend) invite_link is populated.
//   password provided -> combined setup: sets email AND password in one
//     step, no email round-trip; activated:true means they can sign in now.
// The PIN is re-checked here too (same lockout), so this can't be reached by
// skipping the verify-pin step. A real-email account is rejected (409) in
// EITHER mode -- the UI should never call this for one (see needs_setup).
export async function claimInstructor(userId, pin, email, password) {
  const { data } = await client.post('/onboard/claim', {
    user_id: userId, pin, email, ...(password ? { password } : {}),
  })
  return data // { sent, email, invite_link, activated }
}
