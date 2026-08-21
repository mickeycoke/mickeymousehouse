import { useState } from 'react'
import Button from '../ui/Button'
import { createUser } from '../../api/users'
import { getApiErrorMessage } from '../../utils/apiError'

// Inline "the person doesn't exist yet" form — reusable inside any user
// picker. Creates a member-role login and hands the new user back.
// `prefill` carries whatever the user already typed in the picker's search
// box: an address lands in Email, anything else in Full name.
export default function QuickNewUser({ onCreated, onCancel, prefill = '' }) {
  const looksLikeEmail = prefill.includes('@')
  const [name, setName] = useState(looksLikeEmail ? '' : prefill)
  const [email, setEmail] = useState(looksLikeEmail ? prefill : '')
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  async function handleCreate() {
    setSaving(true)
    setError(null)
    try {
      const user = await createUser({ name, email, password, role: 'member' })
      onCreated(user)
    } catch (err) {
      setError(getApiErrorMessage(err, 'Could not create user'))
    } finally {
      setSaving(false)
    }
  }

  const input = 'w-full rounded-lg border border-gray-300 px-3 py-2 text-sm'
  return (
    <div className="flex flex-col gap-2" data-testid="quick-new-user">
      {error && <p className="text-sm text-red-600">{error}</p>}
      <input className={input} placeholder="Full name" value={name}
        onChange={(e) => setName(e.target.value)} data-testid="quick-user-name" />
      <input className={input} placeholder="Email" type="email" value={email}
        onChange={(e) => setEmail(e.target.value)} data-testid="quick-user-email" />
      <input className={input} placeholder="Temporary password" type="text" value={password}
        onChange={(e) => setPassword(e.target.value)} data-testid="quick-user-password" />
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="secondary" onClick={onCancel}>Back</Button>
        <Button size="sm" testId="quick-user-create" loading={saving}
          disabled={!name.trim() || !email.trim() || password.length < 6}
          onClick={handleCreate}>
          Create user
        </Button>
      </div>
    </div>
  )
}
