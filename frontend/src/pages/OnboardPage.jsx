import { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { studioLookup, verifyPin, claimInstructor } from '../api/onboard'
import { getApiErrorMessage } from '../utils/apiError'

// Public instructor onboarding (Phase 1a), outside ProtectedRoute:
//   1) enter your studio code   2) pick your name   3) enter your PIN
//   4) branches on needs_setup:
//        Branch A (no real email on file) — set a NEW email + password, one step
//        Branch B (real email already on file) — nothing to set up; use Forgot password
// then, for Branch A only, a confirmation screen. Styling mirrors LoginPage.
//
// The PIN step is what proves you actually ARE the instructor
// you picked — without it, anyone who knew the studio's public onboard code
// could pick any unclaimed name off the list and set their own email on that
// account. 3 wrong PINs locks the IP out of onboarding for an hour
// (backend-enforced in app/routes/onboard.py; this page just surfaces it).

// Names shown before the "More" button appears — 6 rows of the two-column
// grid. Large studios have dozens of instructors; revealing them a screenful
// at a time beats a scroll area whose edge is easy to miss.
const INSTRUCTOR_PAGE_SIZE = 12

export default function OnboardPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1) // 1 code | 2 name | 3 pin | 4 email | 5 done

  const [code, setCode] = useState('')
  const [studio, setStudio] = useState(null)
  const [instructors, setInstructors] = useState([])
  const [visibleCount, setVisibleCount] = useState(INSTRUCTOR_PAGE_SIZE)
  const [selected, setSelected] = useState(null)
  const [pin, setPin] = useState('')
  // PINs imported from a legacy system can contain letters, which the number
  // pad can't type. Mirrors SharedDeviceLoginPage's same toggle.
  const [typeMode, setTypeMode] = useState(false)
  const [email, setEmail] = useState('')
  // After PIN success, the server says whether this
  // account has a real email on file. true -> Branch A, the combined
  // email+password setup form below. false -> Branch B, "nothing to set up,
  // use Forgot password" — no form at all. null = not yet known.
  const [needsSetup, setNeedsSetup] = useState(null)
  const [confirmEmail, setConfirmEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [searchParams] = useSearchParams()
  const prefill = searchParams.get('studio')

  const runLookup = useCallback(async (raw) => {
    setError('')
    setLoading(true)
    try {
      const data = await studioLookup(raw.trim())
      setStudio(data.studio)
      setInstructors(data.instructors)
      setVisibleCount(INSTRUCTOR_PAGE_SIZE)  // a new studio starts collapsed
      setStep(2)
    } catch (err) {
      setError(getApiErrorMessage(err, "We couldn't find that studio. Check the code and try again."))
    } finally {
      setLoading(false)
    }
  }, [])

  // A studio-owner's QR/link carries ?studio=<code> — skip step 1 straight to
  // picking your name.
  useEffect(() => {
    if (prefill) {
      setCode(prefill)
      runLookup(prefill)
    }
  }, [prefill, runLookup])

  async function handleLookup(e) {
    e.preventDefault()
    runLookup(code)
  }

  function pickInstructor(instructor) {
    setSelected(instructor)
    setPin('')
    setTypeMode(false)
    setError('')
    resetSetupFields()
    setStep(3)
  }

  function resetSetupFields() {
    setNeedsSetup(null)
    setEmail('')
    setConfirmEmail('')
    setPassword('')
    setConfirmPassword('')
  }

  async function submitPin() {
    if (!pin) return
    setError('')
    setLoading(true)
    try {
      const data = await verifyPin(selected.id, pin)
      setNeedsSetup(data.needs_setup)
      setStep(4)
    } catch (err) {
      setPin('')
      setError(getApiErrorMessage(err, 'Incorrect PIN. Try again.'))
    } finally {
      setLoading(false)
    }
  }

  function pressKey(digit) {
    setError('')
    setPin((p) => (p.length >= 12 ? p : p + digit))
  }

  // Branch A: one combined submit sets email AND password.
  // Client-side checks mirror ResetPasswordPage.jsx's password rules, plus a
  // confirm-email field (mitigates losing the old "click a real link" proof
  // that the typed address is actually reachable).
  async function handleSetup(e) {
    e.preventDefault()
    setError('')
    if (email.trim().toLowerCase() !== confirmEmail.trim().toLowerCase()) {
      setError("Email addresses don't match.")
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    if (password !== confirmPassword) {
      setError("Passwords don't match.")
      return
    }
    setLoading(true)
    try {
      await claimInstructor(selected.id, pin, email.trim(), password)
      setStep(5)
    } catch (err) {
      setError(getApiErrorMessage(err, 'Could not set up your account. Try again.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 w-full max-w-sm p-8">
        <h1 className="text-2xl font-semibold text-gray-900 mb-1">Set up your account</h1>
        <p className="text-sm text-gray-500 mb-8" data-testid="onboard-step-label">
          {step === 1 && 'Step 1 of 4 — find your studio'}
          {step === 2 && 'Step 2 of 4 — pick your name'}
          {step === 3 && `Step 3 of 4 — enter ${selected?.name}'s PIN`}
          {step === 4 && needsSetup === true && 'Step 4 of 4 — set your email & password'}
          {step === 4 && needsSetup === false && 'Almost there'}
          {step === 5 && 'All set'}
        </p>

        {/* Step 1 — studio code */}
        {step === 1 && (
          <form onSubmit={handleLookup} noValidate>
            <div className="mb-6">
              <label htmlFor="studio-code" className="block text-sm font-medium text-gray-700 mb-1">
                Studio code
              </label>
              <input
                id="studio-code"
                type="text"
                autoComplete="off"
                autoCapitalize="characters"
                required
                data-testid="onboard-code-input"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm uppercase tracking-widest focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="e.g. ABC234"
              />
              <p className="text-xs text-gray-400 mt-2">
                Ask your studio for its code, or use your original studio ID.
              </p>
            </div>

            {error && <ErrorBanner testid="onboard-error-message">{error}</ErrorBanner>}

            <SubmitButton loading={loading} testid="onboard-code-submit">
              {loading ? 'Looking up…' : 'Continue'}
            </SubmitButton>
          </form>
        )}

        {/* Step 2 — pick your name */}
        {step === 2 && (
          <div>
            <p className="text-sm text-gray-600 mb-3">
              {studio?.name}
            </p>
            {instructors.length === 0 ? (
              <p
                data-testid="onboard-no-instructors"
                className="text-sm text-gray-500 bg-gray-50 border border-gray-200 rounded-lg px-3 py-3"
              >
                No instructors are waiting to be set up for this studio. Ask your studio for help.
              </p>
            ) : (
              <>
                {/* Two columns, no scrolling: a full grid reveals the rest
                    behind an explicit button instead of hiding names below
                    an invisible scroll edge. */}
                <ul className="grid grid-cols-2 gap-2 mb-2" data-testid="onboard-instructor-list">
                  {instructors.slice(0, visibleCount).map((i) => (
                    <li key={i.id}>
                      <button
                        type="button"
                        data-testid="onboard-instructor-option"
                        onClick={() => pickInstructor(i)}
                        className="w-full text-left border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-800 hover:bg-blue-50 hover:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
                      >
                        {i.name}
                      </button>
                    </li>
                  ))}
                </ul>
                {instructors.length > visibleCount && (
                  <button
                    type="button"
                    data-testid="onboard-instructor-more"
                    onClick={() => setVisibleCount((n) => n + INSTRUCTOR_PAGE_SIZE)}
                    className="w-full mb-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
                  >
                    More ({instructors.length - visibleCount} left)
                  </button>
                )}
              </>
            )}

            {/* A deep link (?studio=) skips step 1 entirely, so there's no
                code-entry screen to go "back" to — step 1 would just replay
                the same lookup. Leave the flow instead. */}
            <BackButton onClick={() => {
              if (prefill) navigate('/login')
              else { setStep(1); setError('') }
            }} />
          </div>
        )}

        {/* Step 3 — PIN */}
        {step === 3 && (
          <div data-testid="onboard-pin-step">
            <div className="flex justify-center gap-2 mb-6 h-6" data-testid="onboard-pin-display">
              {pin.length === 0 ? (
                <span className="text-sm text-gray-400">Enter PIN</span>
              ) : (
                Array.from(pin).map((_, idx) => (
                  <span key={idx} className="w-3 h-3 rounded-full bg-gray-700 inline-block" />
                ))
              )}
            </div>

            {error && <ErrorBanner testid="onboard-error-message">{error}</ErrorBanner>}

            {typeMode ? (
              <form onSubmit={(e) => { e.preventDefault(); submitPin() }} className="mb-4">
                <input
                  type="text"
                  autoFocus
                  autoComplete="off"
                  autoCapitalize="none"
                  spellCheck={false}
                  data-testid="onboard-pin-text-input"
                  value={pin}
                  onChange={(e) => { setError(''); setPin(e.target.value.replace(/[^A-Za-z0-9]/g, '').slice(0, 12)) }}
                  placeholder="Enter PIN"
                  className="w-full border border-gray-300 rounded-lg px-3 py-3 text-center text-lg font-mono tracking-widest focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button
                  type="submit"
                  disabled={loading || !pin}
                  data-testid="onboard-pin-submit"
                  className="mt-3 w-full rounded-lg bg-blue-600 text-white text-sm font-medium py-3 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {loading ? '…' : 'Enter'}
                </button>
              </form>
            ) : (
              <div className="grid grid-cols-3 gap-2 mb-4">
                {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => (
                  <PinKey key={d} label={d} onClick={() => pressKey(d)} testid={`onboard-pin-${d}`} />
                ))}
                <PinKey
                  label="⌫"
                  onClick={() => { setError(''); setPin((p) => p.slice(0, -1)) }}
                  testid="onboard-pin-backspace"
                />
                <PinKey label="0" onClick={() => pressKey('0')} testid="onboard-pin-0" />
                <button
                  type="button"
                  disabled={loading || !pin}
                  data-testid="onboard-pin-submit"
                  onClick={submitPin}
                  className="rounded-lg bg-blue-600 text-white text-sm font-medium py-4 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {loading ? '…' : 'Enter'}
                </button>
              </div>
            )}

            <button
              type="button"
              data-testid="onboard-pin-toggle-mode"
              onClick={() => { setPin(''); setError(''); setTypeMode((m) => !m) }}
              className="w-full text-blue-600 text-sm hover:underline focus:outline-none"
            >
              {typeMode ? 'Use the number keypad' : 'My PIN has letters — type it instead'}
            </button>

            <BackButton onClick={() => { setStep(2); setPin(''); setError(''); setTypeMode(false) }} />
          </div>
        )}

        {/* Step 4, Branch A — no real email on file: set email + password together */}
        {step === 4 && needsSetup === true && (
          <form onSubmit={handleSetup} noValidate data-testid="onboard-setup-step">
            <p className="text-sm text-gray-600 mb-4">
              Setting up <span className="font-medium text-gray-900">{selected?.name}</span>
            </p>
            <div className="mb-4">
              <label htmlFor="onboard-email" className="block text-sm font-medium text-gray-700 mb-1">
                Set your email
              </label>
              <input
                id="onboard-email"
                type="email"
                autoComplete="email"
                required
                data-testid="onboard-email-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="you@example.com"
              />
            </div>
            <div className="mb-4">
              <label htmlFor="onboard-email-confirm" className="block text-sm font-medium text-gray-700 mb-1">
                Confirm email
              </label>
              <input
                id="onboard-email-confirm"
                type="email"
                autoComplete="email"
                required
                data-testid="onboard-email-confirm-input"
                value={confirmEmail}
                onChange={(e) => setConfirmEmail(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="you@example.com"
              />
            </div>
            <div className="mb-4">
              <label htmlFor="onboard-password" className="block text-sm font-medium text-gray-700 mb-1">
                New password
              </label>
              <input
                id="onboard-password"
                type="password"
                autoComplete="new-password"
                required
                data-testid="onboard-password-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="••••••••"
              />
            </div>
            <div className="mb-6">
              <label htmlFor="onboard-password-confirm" className="block text-sm font-medium text-gray-700 mb-1">
                Confirm password
              </label>
              <input
                id="onboard-password-confirm"
                type="password"
                autoComplete="new-password"
                required
                data-testid="onboard-password-confirm-input"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="••••••••"
              />
            </div>

            {error && <ErrorBanner testid="onboard-error-message">{error}</ErrorBanner>}

            <SubmitButton loading={loading} testid="onboard-setup-submit">
              {loading ? 'Setting up…' : 'Create my account'}
            </SubmitButton>
            <BackButton onClick={() => { setStep(2); setPin(''); setError(''); resetSetupFields() }} />
          </form>
        )}

        {/* Step 4, Branch B — a real email is already on file: nothing to set
            up, send them to Forgot Password instead. No form, no fields. */}
        {step === 4 && needsSetup === false && (
          <div data-testid="onboard-already-active">
            <p className="text-sm text-gray-600 mb-6">
              <span className="font-medium text-gray-900">{selected?.name}</span>&apos;s account already
              has an email address on file, so there&apos;s nothing to set up here. Use Forgot password
              and we&apos;ll email you a link to get into your account.
            </p>

            <Link
              to="/forgot-password"
              data-testid="onboard-goto-forgot-password"
              className="block w-full text-center bg-blue-600 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors mb-3"
            >
              Forgot password
            </Link>
            <Link
              to="/login"
              data-testid="onboard-goto-login"
              className="block w-full text-center text-gray-500 text-sm hover:text-gray-700"
            >
              Back to sign in
            </Link>

            <BackButton onClick={() => { setStep(2); setPin(''); setError(''); resetSetupFields() }} />
          </div>
        )}

        {/* Step 5 — confirmation (Branch A only; Branch B never reaches this) */}
        {step === 5 && (
          <div data-testid="onboard-confirmation">
            <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-4 text-sm text-green-800 mb-6">
              Your account is ready. Sign in with <span className="font-medium">{email}</span> and the
              password you just chose.
            </div>
            <Link
              to="/login"
              className="block w-full text-center bg-blue-600 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
            >
              Back to sign in
            </Link>
          </div>
        )}

        {step !== 5 && (
          <p className="text-xs text-gray-400 mt-6 text-center">
            Already set up? <Link to="/login" className="text-blue-600 hover:underline">Sign in</Link>
          </p>
        )}
      </div>
    </div>
  )
}

function ErrorBanner({ children, testid }) {
  return (
    <p
      data-testid={testid}
      className="text-red-600 text-sm mb-4 bg-red-50 border border-red-200 rounded-lg px-3 py-2"
    >
      {children}
    </p>
  )
}

function SubmitButton({ children, loading, testid }) {
  return (
    <button
      type="submit"
      disabled={loading}
      data-testid={testid}
      className="w-full bg-blue-600 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
    >
      {children}
    </button>
  )
}

function BackButton({ onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-gray-500 text-sm mt-3 hover:text-gray-700 focus:outline-none"
    >
      ← Back
    </button>
  )
}

function PinKey({ label, onClick, testid }) {
  return (
    <button
      type="button"
      data-testid={testid}
      onClick={onClick}
      className="rounded-lg border border-gray-300 text-lg font-medium text-gray-800 py-4 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
    >
      {label}
    </button>
  )
}
