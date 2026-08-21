import { useEffect, useState } from 'react'
import Button from '../ui/Button'
import { getStudioOwners, assignStudioOwner, updateStudioOwner, removeStudioOwner, getOwnerCandidates } from '../../api/ownership'
import QuickNewUser from '../admin/QuickNewUser'

// Owner + managers of a studio, editable in place. A studio can have multiple
// managers, and a person can hold roles at multiple studios.
//
// Role is set on the person's ROW, not chosen up front:
// the old flow made you pick owner/manager BEFORE clicking a person, silently
// defaulted to manager if you forgot, and gave no way to change it afterward.
// Now you just add the person (as owner) and flip the dropdown on their row
// whenever you like.
export default function StudioPeopleInline({ studioId }) {
  const [people, setPeople] = useState([])
  const [pickerOpen, setPickerOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [candidates, setCandidates] = useState([])
  const [search, setSearch] = useState('')
  const [error, setError] = useState(null)

  function reload() {
    getStudioOwners({ studioId }).then(setPeople).catch(() => setPeople([]))
  }
  useEffect(reload, [studioId])
  useEffect(() => {
    if (!pickerOpen) return
    getOwnerCandidates().then(setCandidates).catch(() => setCandidates([]))
    setSearch(''); setError(null)
  }, [pickerOpen])

  const active = people.filter((p) => p.is_active !== false)
  const taken = new Set(active.map((p) => p.user_id))
  const term = search.trim().toLowerCase()
  const matches = candidates.filter((c) => !taken.has(c.id) &&
    (!term || (c.name || '').toLowerCase().includes(term) || (c.email || '').toLowerCase().includes(term))).slice(0, 8)

  async function add(user) {
    setError(null)
    try {
      // Add as owner by default — the common case, and one click on the row
      // switches it to manager if that's what was meant.
      await assignStudioOwner({ studio_id: studioId, user_id: user.id, level: 'owner' })
      setPickerOpen(false); setCreating(false); reload()
    } catch (err) {
      setError(err.response?.data?.detail?.toString?.() || 'Could not assign this person')
    }
  }

  async function changeLevel(assignmentId, nextLevel) {
    setError(null)
    try {
      await updateStudioOwner(assignmentId, { level: nextLevel })
      reload()
    } catch (err) {
      setError(err.response?.data?.detail?.toString?.() || 'Could not change this role')
    }
  }

  return (
    <div className="mt-4 rounded-lg border border-gray-200" data-testid="studio-people-inline">
      <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">People ({active.length})</p>
        <Button size="sm" variant="secondary" testId="studio-add-person-button" onClick={() => setPickerOpen(true)}>+ Add</Button>
      </div>
      {active.length === 0 && <p className="px-3 py-2 text-sm text-gray-500">No owner or managers yet.</p>}
      {active.map((p) => (
        <div key={p.id} data-testid="studio-person-row" className="flex items-center justify-between gap-2 border-b border-gray-50 px-3 py-2 text-sm last:border-0">
          <span className="min-w-0 flex-1 truncate font-medium text-gray-800">
            {p.user_name || p.user_email || p.user_id}
          </span>
          <div className="flex shrink-0 items-center gap-2">
            <select
              value={p.level === 'manager' ? 'manager' : 'owner'}
              onChange={(e) => changeLevel(p.id, e.target.value)}
              data-testid="studio-person-level"
              className="rounded-lg border border-gray-300 px-2 py-1 text-xs"
            >
              <option value="owner">Owner</option>
              <option value="manager">Manager</option>
            </select>
            <Button size="sm" variant="ghost" testId="studio-person-remove"
              onClick={async () => { await removeStudioOwner(p.id); reload() }}>Remove</Button>
          </div>
        </div>
      ))}

      {pickerOpen && (
        <div className="border-t border-gray-100 px-3 py-3">
          {error && <p className="mb-2 text-sm text-red-600">{error}</p>}
          <p className="mb-2 text-xs text-gray-500">Added as owner — change to manager on their row after.</p>
          {creating ? (
            <QuickNewUser prefill={search.trim()} onCreated={(u) => add(u)} onCancel={() => setCreating(false)} />
          ) : (
            <>
              <input type="text" autoFocus value={search} onChange={(e) => setSearch(e.target.value)}
                placeholder="Search people…" data-testid="studio-person-search"
                className="mb-2 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              <div className="flex max-h-48 flex-col gap-1 overflow-y-auto">
                {matches.map((c) => (
                  <button key={c.id} type="button" data-testid="studio-person-candidate" onClick={() => add(c)}
                    className="rounded-lg border border-gray-200 px-3 py-2 text-left text-sm hover:bg-blue-50">
                    <span className="font-medium">{c.name}</span> <span className="text-gray-500">{c.email}</span>
                  </button>
                ))}
                {matches.length === 0 && <p className="py-2 text-sm text-gray-500">No matches.</p>}
              </div>
              <button type="button" data-testid="studio-person-new-user" onClick={() => setCreating(true)}
                className="mt-2 text-sm font-medium text-blue-600 hover:underline">
                + Person doesn’t exist yet — create a new user
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
