import { useEffect, useState } from 'react'
import AppShell from '../../components/layout/AppShell'
import PageHeader from '../../components/layout/PageHeader'
import Button from '../../components/ui/Button'
import Modal from '../../components/ui/Modal'
import QuickNewUser from '../../components/admin/QuickNewUser'
import {
  getOwnershipScope, getFranchiseOwners, assignFranchiseOwner, removeFranchiseOwner, getOwnerCandidates,
} from '../../api/ownership'
import { sendInvite } from '../../api/auth'
import { getApiErrorMessage } from '../../utils/apiError'

// A franchise owner's self-serve page: add reporting-role users to THEIR
// franchise and invite them onto the platform. Backend forces the reports
// level + own-franchise scope; this page never offers anything else.
export default function FranchiseUsersPage() {
  const [franchiseId, setFranchiseId] = useState(null)
  const [people, setPeople] = useState([])
  const [pickerOpen, setPickerOpen] = useState(false)
  const [candidates, setCandidates] = useState([])
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const [notice, setNotice] = useState(null)   // { kind: 'ok'|'err', text }
  const [busyId, setBusyId] = useState(null)

  function loadPeople(fid) {
    getFranchiseOwners({ franchiseId: fid })
      .then((rows) => setPeople(rows.filter((r) => r.level === 'reports' && r.is_active !== false)))
      .catch(() => setPeople([]))
  }

  useEffect(() => {
    getOwnershipScope()
      .then((scope) => {
        const fid = scope.franchise_ids?.[0] ?? null
        setFranchiseId(fid)
        if (fid) loadPeople(fid)
      })
      .catch(() => setFranchiseId(null))
  }, [])

  useEffect(() => {
    if (!pickerOpen) return
    getOwnerCandidates().then(setCandidates).catch(() => setCandidates([]))
    setSearch(''); setCreating(false)
  }, [pickerOpen])

  const taken = new Set(people.map((p) => p.user_id))
  const term = search.trim().toLowerCase()
  const matches = candidates.filter((c) => !taken.has(c.id) &&
    (!term || (c.name || '').toLowerCase().includes(term) || (c.email || '').toLowerCase().includes(term))).slice(0, 8)

  async function add(user) {
    setNotice(null)
    try {
      await assignFranchiseOwner({ franchise_id: franchiseId, user_id: user.id, level: 'reports' })
      setPickerOpen(false); setCreating(false)
      loadPeople(franchiseId)
    } catch (err) {
      setNotice({ kind: 'err', text: getApiErrorMessage(err, 'Could not add this person') })
    }
  }

  async function invite(userId) {
    setBusyId(userId); setNotice(null)
    try {
      const res = await sendInvite(userId)
      setNotice({ kind: 'ok', text: res?.invite_link
        ? `Invite ready for ${res.email}. Dev link: ${res.invite_link}`
        : `Invite sent to ${res?.email || 'the user'}.` })
      loadPeople(franchiseId)
    } catch (err) {
      setNotice({ kind: 'err', text: getApiErrorMessage(err, 'Could not send the invite') })
    } finally {
      setBusyId(null)
    }
  }

  async function remove(id) {
    await removeFranchiseOwner(id).catch(() => {})
    loadPeople(franchiseId)
  }

  return (
    <AppShell>
      <PageHeader title="Franchise Users" subtitle="Add reporting users and invite them onto the platform" />
      <div className="mx-auto max-w-2xl space-y-4 px-4 py-4 sm:px-8" data-testid="franchise-users-page">
        {!franchiseId && (
          <p className="text-sm text-gray-500">No franchise is linked to your account yet.</p>
        )}

        {notice && (
          <div data-testid="franchise-users-notice"
            className={`rounded-lg border px-3 py-2 text-sm ${notice.kind === 'ok'
              ? 'border-green-200 bg-green-50 text-green-800' : 'border-red-200 bg-red-50 text-red-700'}`}>
            <div className="flex items-start justify-between gap-3">
              <span className="min-w-0 break-words">{notice.text}</span>
              <button onClick={() => setNotice(null)} className="shrink-0 text-xs underline">dismiss</button>
            </div>
          </div>
        )}

        {franchiseId && (
          <div className="rounded-xl border border-gray-200 bg-white">
            <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
              <p className="text-sm font-semibold text-gray-900">Reporting users ({people.length})</p>
              <Button size="sm" testId="franchise-users-add-button" onClick={() => setPickerOpen(true)}>+ Add user</Button>
            </div>
            {people.length === 0 && <p className="px-4 py-3 text-sm text-gray-500">No reporting users yet.</p>}
            {people.map((p) => (
              <div key={p.id} data-testid="franchise-user-row"
                className="flex items-center justify-between gap-3 border-b border-gray-50 px-4 py-2.5 text-sm last:border-0">
                <div className="min-w-0">
                  <p className="truncate font-medium text-gray-800">{p.user_name || p.user_email || p.user_id}</p>
                  <p className="truncate text-xs text-gray-500">
                    {p.user_email}
                    {p.accepted ? ' · active' : p.invited ? ' · invited' : ' · not invited'}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  {!p.accepted && (
                    <Button size="sm" variant="secondary" testId="franchise-user-invite"
                      loading={busyId === p.user_id} onClick={() => invite(p.user_id)}>
                      {p.invited ? 'Resend invite' : 'Send invite'}
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" testId="franchise-user-remove" onClick={() => remove(p.id)}>Remove</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <Modal isOpen={pickerOpen} onClose={() => { setPickerOpen(false); setCreating(false) }} title="Add a reporting user">
        {creating ? (
          <QuickNewUser prefill={search.trim()} onCreated={(u) => add(u)} onCancel={() => setCreating(false)} />
        ) : (
          <>
            <input type="text" autoFocus value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Search people by name or email…" data-testid="franchise-users-search"
              className="mb-3 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            <div className="flex max-h-72 flex-col gap-1 overflow-y-auto">
              {matches.map((c) => (
                <button key={c.id} type="button" data-testid="franchise-users-candidate" onClick={() => add(c)}
                  className="rounded-lg border border-gray-200 px-3 py-2 text-left text-sm hover:border-blue-300 hover:bg-blue-50">
                  <span className="font-medium text-gray-900">{c.name}</span>
                  <span className="ml-1 text-gray-500">{c.email}</span>
                </button>
              ))}
              {matches.length === 0 && <p className="py-4 text-sm text-gray-500">No matches.</p>}
            </div>
            <button type="button" data-testid="franchise-users-new-user" onClick={() => setCreating(true)}
              className="mt-3 text-sm font-medium text-blue-600 hover:underline">
              + Person doesn&apos;t exist yet — create a new user
            </button>
          </>
        )}
      </Modal>
    </AppShell>
  )
}
