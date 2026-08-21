import { useEffect, useState } from 'react'
import AppShell from '../components/layout/AppShell'
import PageHeader from '../components/layout/PageHeader'
import Button from '../components/ui/Button'
import StudioCodesModal from '../components/ownership/StudioCodesModal'
import { useAuth } from '../context/AuthContext'
import { changePassword } from '../api/auth'
import { getStudios } from '../api/ownership'
import { getApiErrorMessage } from '../utils/apiError'

// The user's security groups, from their role "hats" (/roles/me via AuthContext).
function securityGroups(roles) {
  if (!roles) return []
  const studio = roles.studio_name ? ` · ${roles.studio_name}` : ''
  const g = []
  if (roles.base_role === 'admin') g.push('Administrator')
  if (roles.franchise_owner) g.push('Franchise owner')
  if (roles.franchise_manager) g.push('Franchise manager')
  if (roles.studio_owner) g.push(`Studio owner${studio}`)
  if (roles.studio_manager) g.push(`Studio manager${studio}`)
  if (roles.base_role === 'instructor' && !roles.studio_owner && !roles.studio_manager) g.push('Instructor')
  if (roles.is_client) g.push('Client')
  if (!g.length) g.push(roles.base_role || 'Member')
  return g
}

const inputCls = 'mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500'

export default function ProfilePage() {
  const { user, myRoles } = useAuth()
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [msg, setMsg] = useState(null)   // { kind: 'ok' | 'err', text }
  const [saving, setSaving] = useState(false)
  const [myStudios, setMyStudios] = useState([])
  const [codesStudio, setCodesStudio] = useState(null)

  // Studio owners/managers don't see the Studios nav — surface their studios'
  // onboarding/shared-device codes here. (Admins use the Studios page.)
  const managesStudios = (myRoles?.studio_owner || myRoles?.studio_manager) && myRoles?.base_role !== 'admin'
  useEffect(() => {
    if (!managesStudios) return
    getStudios().then(setMyStudios).catch(() => setMyStudios([]))
  }, [managesStudios])

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function submit(e) {
    e.preventDefault()
    setMsg(null)
    if (form.next.length < 8) return setMsg({ kind: 'err', text: 'New password must be at least 8 characters.' })
    if (form.next !== form.confirm) return setMsg({ kind: 'err', text: 'New password and confirmation do not match.' })
    setSaving(true)
    try {
      await changePassword(form.current, form.next)
      setMsg({ kind: 'ok', text: 'Password changed.' })
      setForm({ current: '', next: '', confirm: '' })
    } catch (err) {
      setMsg({ kind: 'err', text: getApiErrorMessage(err, 'Could not change password') })
    } finally {
      setSaving(false)
    }
  }

  const groups = securityGroups(myRoles)

  return (
    <AppShell>
      <PageHeader title="Profile" subtitle="Your account and security groups" />
      <div className="mx-auto max-w-lg space-y-6 px-4 py-4 sm:px-8" data-testid="profile-page">
        <section className="rounded-xl border border-gray-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-gray-900">Account</h2>
          <dl className="mt-3 space-y-1.5 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-gray-500">Name</dt><dd className="truncate text-gray-900">{user?.name}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-gray-500">Email</dt><dd className="truncate text-gray-900">{user?.email}</dd>
            </div>
          </dl>
          <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-gray-500">Security groups</h3>
          <div className="mt-2 flex flex-wrap gap-2" data-testid="profile-groups">
            {groups.map((gp) => (
              <span key={gp} className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">{gp}</span>
            ))}
          </div>
        </section>

        {managesStudios && myStudios.length > 0 && (
          <section className="rounded-xl border border-gray-200 bg-white p-5" data-testid="profile-studio-codes">
            <h2 className="text-sm font-semibold text-gray-900">Instructor onboarding & shared device</h2>
            <p className="mt-1 text-sm text-gray-500">QR codes and links to onboard instructors and set up the front-desk tablet.</p>
            <div className="mt-3 space-y-2">
              {myStudios.map((s) => (
                <div key={s.id} className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 px-3 py-2">
                  <span className="truncate text-sm text-gray-800">{s.display_name || s.name}</span>
                  <Button size="sm" variant="secondary" testId="profile-studio-codes-button" onClick={() => setCodesStudio(s)}>Show codes</Button>
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="rounded-xl border border-gray-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-gray-900">Change password</h2>
          {msg && (
            <p className={`mt-2 text-sm ${msg.kind === 'ok' ? 'text-green-700' : 'text-red-600'}`} data-testid="profile-password-msg">
              {msg.text}
            </p>
          )}
          <form onSubmit={submit} className="mt-3 space-y-3">
            <label className="block text-sm font-medium text-gray-700">Current password
              <input type="password" value={form.current} onChange={set('current')} autoComplete="current-password"
                data-testid="profile-current-password" className={inputCls} />
            </label>
            <label className="block text-sm font-medium text-gray-700">New password
              <input type="password" value={form.next} onChange={set('next')} autoComplete="new-password"
                data-testid="profile-new-password" className={inputCls} />
            </label>
            <label className="block text-sm font-medium text-gray-700">Confirm new password
              <input type="password" value={form.confirm} onChange={set('confirm')} autoComplete="new-password"
                data-testid="profile-confirm-password" className={inputCls} />
            </label>
            <Button type="submit" loading={saving} testId="profile-change-password-button">Change password</Button>
          </form>
        </section>
      </div>

      <StudioCodesModal studio={codesStudio} onClose={() => setCodesStudio(null)} />
    </AppShell>
  )
}
