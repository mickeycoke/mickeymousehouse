// Safety guard: the E2E suite creates and deletes throwaway data (e2e-user-*
// accounts, test franchises/clients/sessions). It must NEVER run against
// production — a misconfigured proxy/backend once spilled that fixture data
// into the prod database. This setup hard-aborts before any test runs if the
// target isn't a local, non-production backend.
import { execSync } from 'node:child_process'
import { cwd } from 'node:process'

export default async function globalSetup(config) {
  const baseURL = config.projects[0]?.use?.baseURL || config.use?.baseURL || ''

  // 1. baseURL must be localhost — never a deployed host.
  const host = (() => { try { return new URL(baseURL).hostname } catch { return '' } })()
  const localHosts = ['localhost', '127.0.0.1', '::1']
  if (!localHosts.includes(host)) {
    throw new Error(
      `E2E ABORTED: baseURL host "${host}" is not local. E2E only runs against ` +
      `localhost. Refusing to touch a remote/deployed target.`)
  }

  // 2. The backend behind the proxy must not be production. Prod reports
  //    {"environment":"production"} from /api/health; anything else is fine.
  let env = 'unknown'
  try {
    const res = await fetch(`${baseURL}/api/health`)
    env = (await res.json())?.environment ?? 'unknown'
  } catch (e) {
    throw new Error(`E2E ABORTED: could not reach ${baseURL}/api/health to verify ` +
      `it is not production (${e.message}). Start the LOCAL stack first.`)
  }
  if (env === 'production') {
    throw new Error(
      'E2E ABORTED: the backend behind this frontend reports environment=production. ' +
      'The E2E suite writes and deletes test data and must never run against prod.')
  }
  // 3. THE SERVER MUST BE SERVING THIS CHECKOUT, AT THIS COMMIT.
  //
  //    This is the guard that was missing. Port 5174 once served a stale `dist`
  //    built from a DIFFERENT checkout; the suite ran against it happily and
  //    produced ~30 phantom failures and a wrong diagnosis before anyone
  //    questioned the port. Six servers were running at one point across two
  //    branches — 5173 and 5178 had genuinely different features.
  //
  //    A port number carries no identity, so vite stamps the branch, commit and
  //    checkout path into a `pt-dev-build` meta tag (see vite.config.js). Here
  //    we compare it with the checkout the tests were launched from. A mismatch
  //    aborts: testing the wrong code is worse than not testing, because it
  //    produces confident, wrong answers.
  let served = ''
  let servedCheckout = ''
  try {
    const html = await (await fetch(`${baseURL}/`)).text()
    served = /name="pt-dev-build"\s+content="([^"]*)"/.exec(html)?.[1] ?? ''
    servedCheckout = /name="pt-dev-checkout"\s+content="([^"]*)"/.exec(html)?.[1] ?? ''
  } catch (e) {
    throw new Error(`E2E ABORTED: could not fetch ${baseURL}/ to identify the ` +
      `served build (${e.message}).`)
  }

  const localSha = (() => {
    try {
      return execSync('git rev-parse --short HEAD', { encoding: 'utf8' }).trim()
    } catch {
      return ''
    }
  })()

  if (!served) {
    throw new Error(
      `E2E ABORTED: ${baseURL} serves no pt-dev-build stamp, so there is no way ` +
      `to tell WHAT it is serving. That is how a stale dist on port 5174 once ` +
      `produced ~30 phantom failures. Restart the dev server from this ` +
      `checkout (npm run dev) so vite can stamp it.`)
  }

  if (localSha && !served.includes(localSha)) {
    throw new Error(
      `E2E ABORTED: ${baseURL} is serving "${served}" but this checkout is at ` +
      `"${localSha}".\n` +
      `  served from: ${servedCheckout || '(unknown)'}\n` +
      `  running in:  ${cwd()}\n` +
      `The suite would be testing code that is not the code you changed. ` +
      `Restart the dev server here, or point E2E_PORT at the right one.`)
  }

  console.log(`[e2e guard] OK — target ${baseURL} is local, backend env="${env}", ` +
    `serving ${served}`)
}
