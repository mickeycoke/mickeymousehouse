import { useEffect, useState } from 'react'
import AppShell from '../../components/layout/AppShell'
import PageHeader from '../../components/layout/PageHeader'
import Badge from '../../components/ui/Badge'
import { ts } from '../../utils/time'
import { getLoginEvents } from '../../api/loginEvents'

// Admin login log: every sign-in attempt across all studios — password logins,
// shared-device PIN logins, and admin impersonation, successes and failures.
const TYPE_LABEL = {
  password: 'Password',
  shared_pin: 'Shared device',
  impersonation: 'Impersonation',
}

export default function LoginLogPage() {
  const [data, setData] = useState(null)
  const [eventType, setEventType] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    setData(null)
    getLoginEvents({
      eventType: eventType || undefined,
      success: success === '' ? undefined : success === 'true',
      limit: 200,
    })
      .then(setData)
      .catch(() => setData({ items: [], total: 0 }))
  }, [eventType, success])

  const fmt = (iso) =>
    iso ? ts(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
    }) : '—'

  const items = data?.items ?? []

  return (
    <AppShell>
      <PageHeader
        title="Login log"
        subtitle="Sign-ins across all studios — password, shared-device PIN, and impersonation"
      />
      <div className="max-w-4xl px-4 py-4 sm:px-8" data-testid="login-log-page">
        <div className="mb-3 flex flex-wrap gap-2">
          <select
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            data-testid="login-log-type-filter"
            className="rounded-lg border border-gray-300 px-2 py-2 text-sm"
          >
            <option value="">All types</option>
            <option value="password">Password</option>
            <option value="shared_pin">Shared device</option>
            <option value="impersonation">Impersonation</option>
          </select>
          <select
            value={success}
            onChange={(e) => setSuccess(e.target.value)}
            data-testid="login-log-success-filter"
            className="rounded-lg border border-gray-300 px-2 py-2 text-sm"
          >
            <option value="">All outcomes</option>
            <option value="true">Success</option>
            <option value="false">Failed</option>
          </select>
        </div>

        {data === null && (
          <p data-loading="true" className="text-sm text-gray-400 animate-pulse">Loading log…</p>
        )}
        {data !== null && items.length === 0 && (
          <p data-testid="empty-state" className="text-sm text-gray-500">No login events match.</p>
        )}

        {items.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                <tr>
                  <th className="px-3 py-2 font-medium">When</th>
                  <th className="px-3 py-2 font-medium">Type</th>
                  <th className="px-3 py-2 font-medium">Outcome</th>
                  <th className="px-3 py-2 font-medium">User</th>
                  <th className="px-3 py-2 font-medium">Studio</th>
                  <th className="px-3 py-2 font-medium">Detail</th>
                  <th className="px-3 py-2 font-medium">IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {items.map((e) => (
                  <tr key={e.id} data-testid="login-log-row" className="align-top">
                    <td className="whitespace-nowrap px-3 py-2 text-gray-700">{fmt(e.created_at)}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-gray-700">{TYPE_LABEL[e.event_type] || e.event_type}</td>
                    <td className="px-3 py-2">
                      <Badge color={e.success ? 'green' : 'red'}>{e.success ? 'success' : 'failed'}</Badge>
                    </td>
                    <td className="px-3 py-2 text-gray-700">
                      <span className="block font-medium text-gray-900">{e.user_name || e.user_email || '—'}</span>
                      {e.actor_name && <span className="block text-xs text-gray-500">by {e.actor_name}</span>}
                    </td>
                    <td className="px-3 py-2 text-gray-700">{e.studio_name || '—'}</td>
                    <td className="px-3 py-2 text-xs text-gray-500">{e.detail || '—'}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-xs text-gray-400">{e.ip_address || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data?.total > items.length && (
          <p className="mt-2 text-xs text-gray-400">Showing the most recent {items.length} of {data.total}.</p>
        )}
      </div>
    </AppShell>
  )
}
