import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { getInviteInfo, setPassword as setPasswordApi } from '../api/auth'
import { getApiErrorMessage } from '../utils/apiError'
import { APP_NAME } from '../config/brand'

const INVALID_LINK_MESSAGE = 'This link is no longer valid — ask your studio for a new one.'

export default function SetPasswordPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''
  const redirectTo = '/admin/overview'

  // 'checking' | 'invalid' | 'form'
  const [status, setStatus] = useState('checking')
  const [inviteError, setInviteError] = useState('')
  const [name, setName] = useState('')

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [formError, setFormError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!token) {
      setInviteError(INVALID_LINK_MESSAGE)
      setStatus('invalid')
      return
    }

    let cancelled = false
    async function checkInvite() {
      try {
        const data = await getInviteInfo(token)
        if (cancelled) return
        if (data.valid) {
          setName(data.name || '')
          setStatus('form')
        } else {
          setInviteError(INVALID_LINK_MESSAGE)
          setStatus('invalid')
        }
      } catch (err) {
        if (cancelled) return
        setInviteError(getApiErrorMessage(err, INVALID_LINK_MESSAGE))
        setStatus('invalid')
      }
    }
    checkInvite()
    return () => { cancelled = true }
  }, [token])

  async function handleSubmit(e) {
    e.preventDefault()
    setFormError('')

    if (password.length < 8) {
      setFormError('Password must be at least 8 characters.')
      return
    }
    if (password !== confirmPassword) {
      setFormError('Passwords do not match.')
      return
    }

    setSubmitting(true)
    try {
      const data = await setPasswordApi(token, password)
      login(data.user, data.access_token)
      navigate(redirectTo, { replace: true })
    } catch (err) {
      setFormError(getApiErrorMessage(err, 'Could not set your password. Try again.'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 w-full max-w-sm p-8">
        <h1 className="text-2xl font-semibold text-gray-900 mb-1">{APP_NAME}</h1>

        {status === 'checking' && (
          <div className="flex flex-col items-center py-6" data-testid="set-password-loading">
            <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin mb-4" />
            <p className="text-sm text-gray-500">Checking your invite link…</p>
          </div>
        )}

        {status === 'invalid' && (
          <>
            <p className="text-sm text-gray-500 mb-6">Set your password</p>
            <p
              data-testid="set-password-invalid-message"
              className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-3 py-2"
            >
              {inviteError}
            </p>
          </>
        )}

        {status === 'form' && (
          <>
            <p className="text-sm text-gray-500 mb-8">
              {name ? `Welcome, ${name}. Set a password to finish setting up your account.` : 'Set a password to finish setting up your account.'}
            </p>

            <form onSubmit={handleSubmit} noValidate>
              <div className="mb-4">
                <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
                  New password
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  data-testid="set-password-input"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="••••••••"
                />
              </div>

              <div className="mb-6">
                <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 mb-1">
                  Confirm password
                </label>
                <input
                  id="confirmPassword"
                  type="password"
                  autoComplete="new-password"
                  required
                  data-testid="set-password-confirm-input"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="••••••••"
                />
              </div>

              {formError && (
                <p
                  data-testid="set-password-error-message"
                  className="text-red-600 text-sm mb-4 bg-red-50 border border-red-200 rounded-lg px-3 py-2"
                >
                  {formError}
                </p>
              )}

              <button
                type="submit"
                disabled={submitting}
                data-testid="set-password-submit-button"
                className="w-full bg-blue-600 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {submitting ? 'Setting password…' : 'Set password'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
