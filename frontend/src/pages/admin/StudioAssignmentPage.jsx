import { useEffect, useState, useCallback } from 'react'
import AppShell from '../../components/layout/AppShell'
import PageHeader from '../../components/layout/PageHeader'
import Badge from '../../components/ui/Badge'
import Button from '../../components/ui/Button'
import { getStudioBacklog, assignStudio } from '../../api/studioAssignment'
import { getApiErrorMessage } from '../../utils/apiError'

// Admin → Studio assignment: clear the studio-less migration backlog. Staff
// that came over without a studio show here, each with a studio SUGGESTED
// from their activity history. Assign one-by-one to its suggestion, or
// bulk-assign a selection to one target studio.
export default function StudioAssignmentPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [note, setNote] = useState(null)
  const [busy, setBusy] = useState(false)

  const [target, setTarget] = useState('')          // bulk target studio id
  const [staffSel, setStaffSel] = useState(() => new Set())

  const load = useCallback(async () => {
    try {
      const d = await getStudioBacklog()
      setData(d)
    } catch (err) {
      setError(getApiErrorMessage(err, 'Failed to load the backlog'))
    }
  }, [])

  useEffect(() => { load() }, [load])

  const studios = data?.studios ?? []
  const staff = data?.staff?.items ?? []

  async function run(payload, successMsg) {
    setBusy(true); setError(null); setNote(null)
    try {
      const res = await assignStudio(payload)
      setNote(successMsg(res))
      setStaffSel(new Set())
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err, 'Assignment failed'))
    } finally {
      setBusy(false)
    }
  }

  const assignToSuggested = (row) => run(
    { studioId: row.suggested_studio_id, userIds: [row.id] },
    (r) => `Assigned ${row.name} → ${r.studio_name}.`,
  )

  const assignSelected = () => {
    const ids = [...staffSel]
    if (!target || ids.length === 0) return
    run(
      { studioId: target, userIds: ids },
      (r) => `Assigned ${r.staff_assigned} staff → ${r.studio_name}.`,
    )
  }

  function toggle(id) {
    setStaffSel((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const targetName = studios.find((s) => s.id === target)?.name

  function Row({ row }) {
    return (
      <div className="flex items-center gap-3 border-b border-gray-100 py-2 last:border-0"
        data-testid="backlog-staff-row">
        <input type="checkbox" checked={staffSel.has(row.id)} onChange={() => toggle(row.id)}
          data-testid="backlog-staff-check"
          className="h-4 w-4 shrink-0 rounded border-gray-300" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-gray-900">{row.name}</span>
          <span className="block truncate text-xs text-gray-500">{row.email || 'no email'}</span>
        </span>
        {row.suggested_studio_id ? (
          <Button size="sm" variant="secondary" testId="assign-suggested-staff"
            disabled={busy} onClick={() => assignToSuggested(row)}>
            → {row.suggested_studio_name}
          </Button>
        ) : (
          <Badge color="gray">no suggestion</Badge>
        )}
      </div>
    )
  }

  return (
    <AppShell>
      <PageHeader
        title="Studio assignment"
        subtitle="Give a studio to migrated staff that came over without one"
      />
      <div className="max-w-3xl space-y-4 px-4 py-4 sm:px-8" data-testid="studio-assignment-page">
        {note && <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-700" data-testid="assign-note">{note}</p>}
        {error && <p className="text-sm text-red-600" data-testid="assign-error">{error}</p>}

        {/* Bulk target picker */}
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3">
          <label className="block text-sm font-medium text-gray-700">
            Bulk assign selected to:
            <select value={target} onChange={(e) => setTarget(e.target.value)}
              data-testid="bulk-target-select"
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
              <option value="">— pick a studio —</option>
              {studios.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
          <p className="mt-1 text-xs text-gray-400">
            Or use each row’s “→ Suggested studio” button to assign it where its activity history points.
          </p>
        </div>

        {/* Staff backlog */}
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3" data-testid="staff-backlog-card">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-sm font-semibold text-gray-800">
              Staff without a studio <Badge color={staff.length ? 'amber' : 'green'}>{data?.staff?.total ?? 0}</Badge>
            </p>
            <Button size="sm" testId="assign-selected-staff" disabled={busy || !target || staffSel.size === 0}
              onClick={assignSelected}>
              Assign {staffSel.size || ''} → {targetName || 'studio'}
            </Button>
          </div>
          {staff.length === 0 ? (
            <p className="text-sm text-gray-500" data-testid="staff-backlog-empty">Everyone has a studio. 🎉</p>
          ) : (
            staff.map((row) => <Row key={row.id} row={row} />)
          )}
        </div>
      </div>
    </AppShell>
  )
}
