import { useState } from 'react'
import { Link } from 'react-router-dom'
import { forgotPassword } from '../api/auth'
import { APP_NAME } from '../config/brand'

// Deliberately generic — shown for every submission regardless of whether
// the email matched a user. Never branch this on the API result shape; the
// backend's response is byte-for-byte identical either way (no enumeration
// tell), and a different message here would defeat that.
const GENERIC_SUCCESS_MESSAGE =
  "If an account exists for that email, we've sent a link to reset your password."

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    try {
      await forgotPassword(email)
    } catch {
      // Fall through to the same generic message even on error — surfacing
      // a distinct failure state here would itself be an enumeration tell.
    } finally {
      setSubmitting(false)
      setSubmitted(true)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 w-full max-w-sm p-8">
        <h1 className="text-2xl font-semibold text-gray-900 mb-1">{APP_NAME}</h1>

        {submitted ? (
          <>
            <p className="text-sm text-gray-500 mb-6">Reset your password</p>
            <p
              data-testid="forgot-password-success-message"
              className="text-sm text-gray-700 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2"
            >
              {GENERIC_SUCCESS_MESSAGE}
            </p>
          </>
        ) : (
          <>
            <p className="text-sm text-gray-500 mb-8">
              Enter your email and we&apos;ll send you a link to reset your password.
            </p>

            <form onSubmit={handleSubmit} noValidate>
              <div className="mb-6">
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  data-testid="forgot-password-email-input"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="you@example.com"
                />
              </div>

              <button
                type="submit"
                disabled={submitting}
                data-testid="forgot-password-submit-button"
                className="w-full bg-blue-600 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {submitting ? 'Sending…' : 'Send reset link'}
              </button>
            </form>
          </>
        )}

        <Link
          to="/login"
          data-testid="forgot-password-back-to-login-link"
          className="block text-center text-gray-500 text-sm mt-6 hover:text-gray-700"
        >
          Back to sign in
        </Link>
      </div>
    </div>
  )
}
