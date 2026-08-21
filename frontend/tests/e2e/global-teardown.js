// Runs once after the whole suite: retire the studios the specs created.
//
// A per-spec afterAll would not be enough - the 84 stale studios in dev came
// from runs that crashed or were interrupted part-way. This runs even then, and
// it works by name prefix rather than by remembering ids, so it also sweeps up
// after previous runs.
import { request as playwrightRequest } from '@playwright/test'
import { deactivateE2EStudios } from './helpers/studios.js'

export default async function globalTeardown() {
  const request = await playwrightRequest.newContext()
  try {
    const { retired, reason } = await deactivateE2EStudios(request)
    if (reason) {
      console.log(`[e2e teardown] could not retire test studios: ${reason}`)
    } else {
      console.log(`[e2e teardown] retired ${retired} test studio(s)`)
    }
  } catch (err) {
    // Never fail the run over cleanup - the results are what matter.
    console.log(`[e2e teardown] skipped: ${err.message}`)
  } finally {
    await request.dispose()
  }
}
