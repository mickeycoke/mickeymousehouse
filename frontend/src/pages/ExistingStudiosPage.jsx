import { useState } from 'react'
import { Link } from 'react-router-dom'
import { studioLookup } from '../api/onboard'
import { getApiErrorMessage } from '../utils/apiError'

// PUBLIC "Existing Studios" flow:
//
//   sign-in screen — a QUIET "Existing Studios" button
//     → this screen, step 1 — enter your studio code
//     → this screen, step 2 — PROMINENT "Shared Studio Device Login"
//                             quiet "Instructor Setup"
//
// The order is the point: the front desk must know the code, and it is the
// point of entry for all studios. So the code comes FIRST, before either
// destination is offered — it is the thing that identifies the studio, not a
// hurdle placed after the choice. Both buttons below it are already scoped to
// the studio the code resolved.
//
// It sits OUTSIDE ProtectedRoute on purpose: the code is entered before anyone
// can sign in, so a login gate here would be a closed loop.
//
// The lookup is the same public endpoint /onboard already calls, so this adds
// no new backend surface. Styling mirrors LoginPage and OnboardPage.
export default function ExistingStudiosPage() {
  const [code, setCode] = useState('')
  const [studio, setStudio] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleLookup(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await studioLookup(code.trim())
      setStudio(data.studio)
    } catch (err) {
      setError(getApiErrorMessage(
        err, "We couldn't find that studio. Check the code and try again."))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 w-full max-w-sm p-8">
        <h1 className="text-2xl font-semibold text-gray-900 mb-1">Existing studios</h1>
        <p className="text-sm text-gray-500 mb-8">
          {studio ? studio.name : 'Enter your studio code to continue.'}
        </p>

        {!studio && (
          <form onSubmit={handleLookup} noValidate>
            <label htmlFor="existing-studio-code" className="block text-sm font-medium text-gray-700 mb-1">
              Studio code
            </label>
            <input
              id="existing-studio-code"
              type="text"
              autoComplete="off"
              autoCapitalize="characters"
              required
              data-testid="existing-studios-code-input"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm uppercase tracking-widest focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="e.g. ABC234"
            />
            <p className="mt-1 text-xs text-gray-400">
              Your studio&rsquo;s code, or its original studio ID.
            </p>

            {error && (
              <p
                data-testid="existing-studios-error"
                className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600"
              >
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading || !code.trim()}
              data-testid="existing-studios-code-submit"
              className="mt-4 w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? 'Checking…' : 'Continue'}
            </button>
          </form>
        )}

        {studio && (
          <div data-testid="existing-studios-options">
            {/* PROMINENT — the everyday door, used by every studio.
                The code was just validated here, so it travels on and /shared
                opens straight on the instructor list rather than asking for
                the same code a second time. */}
            <Link
              to={`/shared?studio=${encodeURIComponent(code.trim())}`}
              data-testid="existing-studios-shared-device-link"
              className="block w-full rounded-lg bg-blue-700 px-4 py-4 text-center text-base font-semibold text-white transition-colors hover:bg-blue-800"
            >
              Shared Studio Device Login
            </Link>
            <p className="mt-2 text-xs text-gray-500">
              For the studio&rsquo;s front-desk device. Pick your name and enter
              your PIN.
            </p>

            {/* The other everyday errand from this screen: onboard a new
                instructor. Public, same as Shared Studio Device Login above —
                no login needed, and it's the same /onboard flow the QR codes
                on the studio's own codes page point to. Carries the resolved
                code through like its sibling above. */}
            <Link
              to={`/onboard?studio=${encodeURIComponent(code.trim())}`}
              data-testid="existing-studios-instructor-setup-link"
              className="mt-3 block w-full rounded-lg border border-gray-300 px-4 py-3 text-center text-sm font-medium text-gray-700 transition-colors hover:border-gray-400 hover:bg-gray-50"
            >
              Instructor Setup
            </Link>

            <button
              type="button"
              data-testid="existing-studios-change-studio"
              onClick={() => { setStudio(null); setError('') }}
              className="mt-6 block w-full text-center text-sm text-gray-500 hover:text-gray-700"
            >
              Use a different studio code
            </button>
          </div>
        )}

        <Link
          to="/login"
          data-testid="existing-studios-back-to-login-link"
          className="mt-8 block text-center text-sm text-gray-500 hover:text-gray-700"
        >
          Back to sign in
        </Link>
      </div>
    </div>
  )
}
