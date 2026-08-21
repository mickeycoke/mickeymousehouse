import { useEffect, useState } from 'react'
import Modal from '../ui/Modal'
import Button from '../ui/Button'
import { setUserRoles } from '../../api/roles'
import { getStudios, getFranchises } from '../../api/ownership'
import { getApiErrorMessage } from '../../utils/apiError'

// Final role model. Checkboxes on the user record:
//   franchise manager / franchise reports / studio owner / studio manager /
//   instructor. One franchise per user. One studio per user.
export default function RolesEditor({ user, hats, isOpen, onClose, onSaved }) {
  const [studios, setStudios] = useState([])
  const [franchises, setFranchises] = useState([])
  const [isInstructor, setIsInstructor] = useState(false)
  const [franchiseId, setFranchiseId] = useState('')
  const [franchiseLevel, setFranchiseLevel] = useState('')   // '' | manager | reports
  const [studioRoles, setStudioRoles] = useState([])         // [{ studio_id, level }] — multi-studio
  const [homeStudioId, setHomeStudioId] = useState('')
  const [instructorStudios, setInstructorStudios] = useState([])  // studios they teach at (ids)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!isOpen) return
    getStudios().then(setStudios).catch(() => setStudios([]))
    getFranchises().then(setFranchises).catch(() => setFranchises([]))
  }, [isOpen])

  useEffect(() => {
    if (!isOpen || !user) return
    setIsInstructor(user.role === 'instructor' || user.role === 'manager')
    const fo = hats?.franchise_owner_of?.[0]
    const fm = hats?.franchise_manager_of?.[0]
    const fr = hats?.franchise_reports_of?.[0]
    setFranchiseLevel(fo ? 'owner' : fm ? 'manager' : fr ? 'reports' : '')
    setFranchiseId('')  // resolved by name after franchises load (see below)
    setStudioRoles([])   // hydrated by id once the studios list loads (below)
    setHomeStudioId(user.studio_id || '')
    setInstructorStudios(hats?.instructor_studio_ids ?? [])
    setError(null)
  }, [isOpen, user, hats])

  // Map current hat NAMES to ids once the lists arrive
  useEffect(() => {
    if (!isOpen) return
    const fname = hats?.franchise_owner_of?.[0] || hats?.franchise_manager_of?.[0] || hats?.franchise_reports_of?.[0]
    if (fname) {
      const f = franchises.find((x) => x.name === fname)
      if (f) setFranchiseId(f.id)
    }
    const idByName = (name) => studios.find((x) => (x.display_name || x.name) === name)?.id
    const owners = (hats?.studio_owner_of ?? []).map((n) => ({ studio_id: idByName(n), level: 'owner' }))
    const managers = (hats?.studio_manager_of ?? []).map((n) => ({ studio_id: idByName(n), level: 'manager' }))
    const rows = [...owners, ...managers].filter((r) => r.studio_id)
    if (rows.length) setStudioRoles(rows)
  }, [isOpen, franchises, studios, hats])

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      await setUserRoles(user.id, {
        is_admin: user.role === 'admin',
        is_instructor: isInstructor,
        franchise_id: franchiseLevel ? (franchiseId || null) : null,
        franchise_level: franchiseLevel || 'manager',
        studio_roles: studioRoles.filter((r) => r.studio_id),
        home_studio_id: (isInstructor ? (homeStudioId || instructorStudios[0]) : homeStudioId) || null,
        instructor_studio_ids: isInstructor ? instructorStudios : [],
      })
      onSaved?.()
      onClose()
    } catch (err) {
      setError(getApiErrorMessage(err, 'Failed to save roles'))
    } finally {
      setSaving(false)
    }
  }

  if (!user) return null
  const check = 'flex items-center gap-2 py-1.5 text-sm text-gray-800'
  const select = 'mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm'

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`Roles — ${user.name}`}>
      <div className="flex max-h-[65vh] flex-col gap-1 overflow-y-auto" data-testid="roles-editor">
        {error && <p className="text-sm text-red-600">{error}</p>}
        {user.role === 'admin' && (
          <p className="mb-1 rounded bg-purple-50 px-2 py-1 text-xs text-purple-700">Admin account — has every permission regardless of roles below.</p>
        )}

        <label className={check}>
          <input type="checkbox" data-testid="role-franchise-owner"
            checked={franchiseLevel === 'owner'}
            onChange={(e) => setFranchiseLevel(e.target.checked ? 'owner' : (franchiseLevel === 'owner' ? '' : franchiseLevel))} />
          Franchise owner <span className="text-xs text-gray-400">(franchise report only + invite reporting users)</span>
        </label>
        <label className={check}>
          <input type="checkbox" data-testid="role-franchise-reports"
            checked={franchiseLevel === 'reports'}
            onChange={(e) => setFranchiseLevel(e.target.checked ? 'reports' : (franchiseLevel === 'reports' ? '' : franchiseLevel))} />
          Franchise reports only <span className="text-xs text-gray-400">(view the franchise report, nothing else)</span>
        </label>
        <label className={check}>
          <input type="checkbox" data-testid="role-franchise-manager"
            checked={franchiseLevel === 'manager'}
            onChange={(e) => setFranchiseLevel(e.target.checked ? 'manager' : (franchiseLevel === 'manager' ? '' : franchiseLevel))} />
          Franchise manager <span className="text-xs text-gray-400">(operations — studios setup, studio owners)</span>
        </label>
        {franchiseLevel && (
          <select value={franchiseId} data-testid="role-franchise-select"
            onChange={(e) => setFranchiseId(e.target.value)} className={select}>
            <option value="">— pick the franchise (one per user) —</option>
            {franchises.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        )}

        <div className="py-1.5">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-800">Studio owner / manager</span>
            <button type="button" data-testid="role-add-studio"
              onClick={() => setStudioRoles((rs) => [...rs, { studio_id: '', level: 'owner' }])}
              className="text-xs font-medium text-blue-600 hover:underline">+ Add studio</button>
          </div>
          <p className="text-xs text-gray-400">Owner: full studio setup + reports. Manager: acts on the owner&apos;s behalf. A user can hold roles at several studios.</p>
          {studioRoles.length === 0 && <p className="mt-1 text-xs text-gray-400">No studio owner/manager roles.</p>}
          {studioRoles.map((r, i) => (
            <div key={i} className="mt-1.5 flex items-center gap-2" data-testid="role-studio-row">
              <select value={r.studio_id} data-testid="role-studio-select"
                onChange={(e) => setStudioRoles((rs) => rs.map((x, j) => (j === i ? { ...x, studio_id: e.target.value } : x)))}
                className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm">
                <option value="">— pick a studio —</option>
                {studios.map((s) => <option key={s.id} value={s.id}>{s.display_name || s.name}</option>)}
              </select>
              <select value={r.level} data-testid="role-studio-level"
                onChange={(e) => setStudioRoles((rs) => rs.map((x, j) => (j === i ? { ...x, level: e.target.value } : x)))}
                className="rounded-lg border border-gray-300 px-2 py-2 text-sm">
                <option value="owner">Owner</option>
                <option value="manager">Manager</option>
              </select>
              <button type="button" aria-label="Remove studio" data-testid="role-studio-remove"
                onClick={() => setStudioRoles((rs) => rs.filter((_, j) => j !== i))}
                className="shrink-0 rounded-lg px-2 py-2 text-gray-400 hover:text-red-600">✕</button>
            </div>
          ))}
        </div>

        <label className={check}>
          <input type="checkbox" data-testid="role-instructor"
            checked={isInstructor} onChange={(e) => setIsInstructor(e.target.checked)} />
          Instructor <span className="text-xs text-gray-400">(day-to-day studio operations)</span>
        </label>
        {isInstructor && (
          <div className="pl-6" data-testid="role-instructor-studios">
            <p className="mb-1 text-xs text-gray-400">Studios they teach at (mark one as primary for kiosk sign-in):</p>
            <div className="max-h-44 space-y-1 overflow-y-auto rounded-lg border border-gray-200 p-2">
              {studios.map((s) => {
                const checked = instructorStudios.includes(s.id)
                return (
                  <div key={s.id} className="flex items-center justify-between gap-2 text-sm" data-testid="role-instructor-studio-row">
                    <label className="flex min-w-0 items-center gap-2">
                      <input type="checkbox" checked={checked}
                        onChange={(e) => {
                          setInstructorStudios((xs) => (e.target.checked ? [...xs, s.id] : xs.filter((x) => x !== s.id)))
                          if (!e.target.checked && homeStudioId === s.id) setHomeStudioId('')
                          if (e.target.checked && !homeStudioId) setHomeStudioId(s.id)
                        }} />
                      <span className="truncate">{s.display_name || s.name}</span>
                    </label>
                    {checked && (
                      <label className="flex shrink-0 items-center gap-1 text-xs text-gray-500">
                        <input type="radio" name="roles-editor-home-studio" checked={homeStudioId === s.id}
                          onChange={() => setHomeStudioId(s.id)} />
                        primary
                      </label>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 flex justify-end gap-3">
        <Button variant="secondary" testId="roles-cancel-button" onClick={onClose}>Cancel</Button>
        <Button testId="roles-save-button" loading={saving} onClick={handleSave}>Save roles</Button>
      </div>
    </Modal>
  )
}
