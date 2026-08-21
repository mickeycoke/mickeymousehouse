import { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { sharedLookup, sharedLogin } from '../api/auth'
import { getApiErrorMessage } from '../utils/apiError'

// Public shared-device login (Phase 1b), outside ProtectedRoute:
//   1) enter the studio/group code  2) pick a name  3) enter the PIN
// On success the short-lived, studio-scoped token is stored like a normal login.
export default function SharedDeviceLoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()

  const [step, setStep] = useState(1) // 1 code | 2 name | 3 pin
  const [code, setCode] = useState('')
  const [studio, setStudio] = useState(null)
  const [instructors, setInstructors] = useState([])
  const [selected, setSelected] = useState(null)
  const [pin, setPin] = useState('')
  // PINs imported from a legacy system can contain letters, which the number pad
  // can't type. This flips step 3 to a plain text field for them; the keypad
  // stays the default because that's what most people use.
  const [typeMode, setTypeMode] = useState(false)

  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [searchParams] = useSearchParams()
  const prefill = searchParams.get('studio')

  const runLookup = useCallback(async (raw) => {
    setError('')
    setLoading(true)
    try {
      const data = await sharedLookup(raw.trim())
      setStudio(data.studio)
      setInstructors(data.instructors)
      setStep(2)
    } catch (err) {
      setError(getApiErrorMessage(err, "We couldn't find that studio. Check the code and try again."))
    } finally {
      setLoading(false)
    }
  }, [])

  // The studio's kiosk QR/link carries ?studio=<code> — the tablet lands straight
  // on the name grid, ready for an instructor's PIN.
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
    setError('')
    setTypeMode(false)
    setStep(3)
  }

  async function submitPin() {
    if (!pin) return
    setError('')
    setLoading(true)
    try {
      const data = await sharedLogin(code.trim(), selected.id, pin)
      login(data.user, data.access_token)
      navigate('/admin/overview', { replace: true })
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

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 w-full max-w-sm p-8">
        <h1 className="text-2xl font-semibold text-gray-900 mb-1">Studio sign in</h1>
        <p className="text-sm text-gray-500 mb-8">
          {step === 1 && 'Enter your studio code'}
          {step === 2 && 'Choose your name'}
          {step === 3 && `Enter ${selected?.name}'s PIN`}
        </p>

        {/* Step 1 — studio code */}
        {step === 1 && (
          <form onSubmit={handleLookup} noValidate>
            <div className="mb-6">
              <label htmlFor="shared-code" className="block text-sm font-medium text-gray-700 mb-1">
                Studio code
              </label>
              <input
                id="shared-code"
                type="text"
                autoComplete="off"
                autoCapitalize="characters"
                required
                data-testid="shared-code-input"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm uppercase tracking-widest focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="e.g. ABC234"
              />
            </div>

            {error && <ErrorBanner testid="shared-error-message">{error}</ErrorBanner>}

            <button
              type="submit"
              disabled={loading}
              data-testid="shared-code-submit"
              className="w-full bg-blue-600 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Looking up…' : 'Continue'}
            </button>
          </form>
        )}

        {/* Step 2 — name grid */}
        {step === 2 && (
          <div>
            <p className="text-sm text-gray-600 mb-3">{studio?.name}</p>
            {instructors.length === 0 ? (
              <p
                data-testid="shared-no-instructors"
                className="text-sm text-gray-500 bg-gray-50 border border-gray-200 rounded-lg px-3 py-3"
              >
                No instructors have a PIN set for this studio yet.
              </p>
            ) : (
              <div className="grid grid-cols-2 gap-2 mb-2 max-h-72 overflow-y-auto" data-testid="shared-instructor-grid">
                {instructors.map((i) => (
                  <button
                    key={i.id}
                    type="button"
                    data-testid="shared-instructor-option"
                    onClick={() => pickInstructor(i)}
                    className="border border-gray-300 rounded-lg px-3 py-3 text-sm text-gray-800 hover:bg-blue-50 hover:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
                  >
                    {i.name}
                  </button>
                ))}
              </div>
            )}
            <BackButton onClick={() => { setStep(1); setError('') }} />
          </div>
        )}

        {/* Step 3 — PIN pad */}
        {step === 3 && (
          <div data-testid="shared-pin-step">
            <div className="flex justify-center gap-2 mb-6 h-6" data-testid="shared-pin-display">
              {pin.length === 0 ? (
                <span className="text-sm text-gray-400">Enter PIN</span>
              ) : (
                Array.from(pin).map((_, idx) => (
                  <span key={idx} className="w-3 h-3 rounded-full bg-gray-700 inline-block" />
                ))
              )}
            </div>

            {error && <ErrorBanner testid="shared-error-message">{error}</ErrorBanner>}

            {typeMode ? (
              // Letters-and-numbers PIN: a plain field the keypad can't offer.
              <form onSubmit={(e) => { e.preventDefault(); submitPin() }} className="mb-4">
                <input
                  type="text"
                  autoFocus
                  autoComplete="off"
                  autoCapitalize="none"
                  spellCheck={false}
                  data-testid="shared-pin-text-input"
                  value={pin}
                  onChange={(e) => { setError(''); setPin(e.target.value.replace(/[^A-Za-z0-9]/g, '').slice(0, 12)) }}
                  placeholder="Enter PIN"
                  className="w-full border border-gray-300 rounded-lg px-3 py-3 text-center text-lg font-mono tracking-widest focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button
                  type="submit"
                  disabled={loading || !pin}
                  data-testid="shared-pin-submit"
                  className="mt-3 w-full rounded-lg bg-blue-600 text-white text-sm font-medium py-3 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {loading ? '…' : 'Enter'}
                </button>
              </form>
            ) : (
              <div className="grid grid-cols-3 gap-2 mb-4">
                {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => (
                  <PinKey key={d} label={d} onClick={() => pressKey(d)} testid={`shared-pin-${d}`} />
                ))}
                <PinKey
                  label="⌫"
                  onClick={() => { setError(''); setPin((p) => p.slice(0, -1)) }}
                  testid="shared-pin-backspace"
                />
                <PinKey label="0" onClick={() => pressKey('0')} testid="shared-pin-0" />
                <button
                  type="button"
                  disabled={loading || !pin}
                  data-testid="shared-pin-submit"
                  onClick={submitPin}
                  className="rounded-lg bg-blue-600 text-white text-sm font-medium py-4 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {loading ? '…' : 'Enter'}
                </button>
              </div>
            )}

            {/* Legacy-imported PINs can contain letters — offer the field. */}
            <button
              type="button"
              data-testid="shared-pin-toggle-mode"
              onClick={() => { setPin(''); setError(''); setTypeMode((m) => !m) }}
              className="w-full text-blue-600 text-sm hover:underline focus:outline-none"
            >
              {typeMode ? 'Use the number keypad' : 'My PIN has letters — type it instead'}
            </button>

            <BackButton onClick={() => { setStep(2); setPin(''); setError(''); setTypeMode(false) }} />
          </div>
        )}

        <p className="text-xs text-gray-400 mt-6 text-center">
          Own device? <Link to="/login" className="text-blue-600 hover:underline">Sign in with email</Link>
        </p>
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
