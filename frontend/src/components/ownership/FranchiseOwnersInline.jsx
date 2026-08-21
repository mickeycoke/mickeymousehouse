import { useEffect, useState } from 'react'
import Button from '../ui/Button'
import Modal from '../ui/Modal'
import {
  getFranchiseOwners, assignFranchiseOwner, removeFranchiseOwner, getOwnerCandidates,
} from '../../api/ownership'
import QuickNewUser from '../admin/QuickNewUser'

// Owners, right on the franchise edit page: current owners listed, and an
// "Add owner" popup with search — no separate two-panel screen needed.
export default function FranchiseOwnersInline({ franchiseId }) {
  const [owners, setOwners] = useState([])
  const [pickerOpen, setPickerOpen] = useState(false)
  const [candidates, setCandidates] = useState([])
  const [search, setSearch] = useState('')
  const [level, setLevel] = useState('owner')
  const [creating, setCreating] = useState(false)

  function reload() {
    getFranchiseOwners({ franchiseId }).then(setOwners).catch(() => setOwners([]))
  }
  useEffect(reload, [franchiseId])

  useEffect(() => {
    if (!pickerOpen) return
    getOwnerCandidates().then(setCandidates).catch(() => setCandidates([]))
    setSearch('')
  }, [pickerOpen])

  const activeOwners = owners.filter((o) => o.is_active !== false)
  const ownerIds = new Set(activeOwners.map((o) => o.user_id))
  const term = search.trim().toLowerCase()
  const matches = candidates.filter((c) =>
    !ownerIds.has(c.id) &&
    (!term || (c.name || '').toLowerCase().includes(term) || (c.email || '').toLowerCase().includes(term))
  ).slice(0, 8)

  async function add(user) {
    await assignFranchiseOwner({ franchise_id: franchiseId, user_id: user.id, level })
    setPickerOpen(false)
    setCreating(false)
    reload()
  }

  return (
    <div className="mt-6 rounded-lg border border-gray-200 bg-white" data-testid="franchise-owners-inline">
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2.5">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
          Owners ({activeOwners.length})
        </p>
        <Button size="sm" variant="secondary" testId="franchise-add-owner-button" onClick={() => setPickerOpen(true)}>
          + Add owner
        </Button>
      </div>
      {activeOwners.length === 0 && (
        <p className="px-4 py-3 text-sm text-gray-500">No owners yet.</p>
      )}
      {activeOwners.map((o) => (
        <div key={o.id} data-testid="franchise-owner-row"
          className="flex items-center justify-between border-b border-gray-50 px-4 py-2 text-sm last:border-0">
          <span className="font-medium text-gray-800">
            {o.user_name || o.user_email || o.user_id}
            {o.user_email && o.user_name && <span className="ml-1 font-normal text-gray-400">({o.user_email})</span>}
            <span className={`ml-2 rounded-full px-2 py-0.5 text-xs ${o.level === 'reports' ? 'bg-gray-100 text-gray-600' : o.level === 'owner' ? 'bg-blue-100 text-blue-800' : 'bg-amber-100 text-amber-800'}`}>
              {o.level === 'reports' ? 'reports only' : o.level === 'owner' ? 'franchise owner' : 'manager (ops)'}
            </span>
          </span>
          <Button size="sm" variant="ghost" testId="franchise-owner-remove"
            onClick={async () => { await removeFranchiseOwner(o.id); reload() }}>
            Remove
          </Button>
        </div>
      ))}

      <Modal isOpen={pickerOpen} onClose={() => { setPickerOpen(false); setCreating(false) }} title="Add to franchise">
        <div className="mb-3 flex flex-wrap gap-4 text-sm">
          <label className="flex items-center gap-1.5">
            <input type="radio" name="fr-level" checked={level === 'owner'}
              onChange={() => setLevel('owner')} data-testid="add-owner-level-owner" />
            Franchise owner <span className="text-gray-400">(reports + invite)</span>
          </label>
          <label className="flex items-center gap-1.5">
            <input type="radio" name="fr-level" checked={level === 'reports'}
              onChange={() => setLevel('reports')} data-testid="add-owner-level-reports" />
            Reports only
          </label>
          <label className="flex items-center gap-1.5">
            <input type="radio" name="fr-level" checked={level === 'manager'}
              onChange={() => setLevel('manager')} data-testid="add-owner-level-manager" />
            Manager <span className="text-gray-400">(operations)</span>
          </label>
        </div>
        {creating ? (
          <QuickNewUser prefill={search.trim()} onCreated={(u) => add(u)} onCancel={() => setCreating(false)} />
        ) : (
        <>
        <input
          type="text"
          autoFocus
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search people by name or email…"
          data-testid="add-owner-search"
          className="mb-3 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <div className="flex max-h-72 flex-col gap-1 overflow-y-auto">
          {matches.map((c) => (
            <button key={c.id} type="button" data-testid="add-owner-candidate"
              onClick={() => add(c)}
              className="rounded-lg border border-gray-200 px-3 py-2 text-left text-sm hover:border-blue-300 hover:bg-blue-50">
              <span className="font-medium text-gray-900">{c.name}</span>
              <span className="ml-1 text-gray-500">{c.email}</span>
            </button>
          ))}
          {matches.length === 0 && <p className="py-4 text-sm text-gray-500">No matches.</p>}
        </div>
        <button type="button" data-testid="add-owner-new-user"
          onClick={() => setCreating(true)}
          className="mt-3 text-sm font-medium text-blue-600 hover:underline">
          + Person doesn&apos;t exist yet — create a new user
        </button>
        </>
        )}
      </Modal>
    </div>
  )
}
