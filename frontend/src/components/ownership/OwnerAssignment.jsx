import { useMemo, useState } from 'react'
import Button from '../ui/Button'
import Badge from '../ui/Badge'
import { getApiErrorMessage } from '../../utils/apiError'

export default function OwnerAssignment({
  title = 'Assign owner',
  ownerCandidates = [],
  assignments = [],
  ownerLabel = (owner) => owner.name || owner.email,
  assignmentLabel = (assignment) => assignment.user_name || assignment.user_email || assignment.user_id,
  loading = false,
  error = null,
  onAssign,
  onRemove,
  onInvite,
}) {
  const [userId, setUserId] = useState('')
  const [notes, setNotes] = useState('')
  const [search, setSearch] = useState('')
  const [saving, setSaving] = useState(false)
  // Per-assignment invite UI state, keyed by assignment id: { sending, message, error }
  const [inviteStates, setInviteStates] = useState({})

  const activeAssignments = useMemo(
    () => assignments.filter((assignment) => assignment.is_active !== false),
    [assignments]
  )
  const activeUserIds = useMemo(
    () => new Set(activeAssignments.map((assignment) => assignment.user_id)),
    [activeAssignments]
  )
  const availableOwnerCandidates = useMemo(() => {
    const term = search.trim().toLowerCase()
    return ownerCandidates.filter((owner) => {
      if (activeUserIds.has(owner.id)) return false
      if (!term) return true
      return (owner.name || '').toLowerCase().includes(term)
        || (owner.email || '').toLowerCase().includes(term)
    })
  }, [ownerCandidates, activeUserIds, search])

  async function handleAssign(event) {
    event.preventDefault()
    if (!userId || !onAssign) return
    setSaving(true)
    try {
      await onAssign({ user_id: userId, notes: notes || undefined })
      setUserId('')
      setNotes('')
    } finally {
      setSaving(false)
    }
  }

  async function handleInvite(assignment) {
    if (!onInvite) return
    setInviteStates((prev) => ({ ...prev, [assignment.id]: { sending: true, message: null, error: null } }))
    try {
      const result = await onInvite(assignment.user_id)
      const message = result?.invite_link
        ? `Setup email sent to ${result.email}. Dev link: ${result.invite_link}`
        : `Setup email sent to ${result?.email || 'the owner'}.`
      setInviteStates((prev) => ({ ...prev, [assignment.id]: { sending: false, message, error: null } }))
    } catch (err) {
      setInviteStates((prev) => ({
        ...prev,
        [assignment.id]: { sending: false, message: null, error: getApiErrorMessage(err, 'Failed to send setup email') },
      }))
    }
  }

  return (
    <div className="space-y-4" data-testid="owner-assignment">
      <div>
        <h2 className="text-base font-semibold text-gray-900">{title}</h2>
        {error && <p className="text-sm text-red-600 mt-1">{error}</p>}
      </div>

      <input
        type="text"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Search people by name or email…"
        data-testid="owner-search-input"
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
      />

      <form onSubmit={handleAssign} className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <label className="flex-1 text-sm font-medium text-gray-700">
          Owner ({availableOwnerCandidates.length} match{availableOwnerCandidates.length === 1 ? '' : 'es'})
          <select
            value={userId}
            onChange={(event) => setUserId(event.target.value)}
            disabled={loading || saving}
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            data-testid="owner-assignment-user"
          >
            <option value="">Select owner</option>
            {availableOwnerCandidates.map((owner) => (
              <option key={owner.id} value={owner.id}>
                {ownerLabel(owner)}
              </option>
            ))}
          </select>
        </label>

        <label className="flex-1 text-sm font-medium text-gray-700">
          Notes
          <input
            type="text"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            disabled={loading || saving}
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            data-testid="owner-assignment-notes"
          />
        </label>

        <Button type="submit" loading={saving} disabled={!userId || loading} testId="owner-assignment-submit">
          Assign
        </Button>
      </form>

      <div className="rounded-lg border border-gray-200 bg-white">
        {activeAssignments.length === 0 ? (
          <p className="px-4 py-3 text-sm text-gray-500">No active owners assigned.</p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {activeAssignments.map((assignment) => {
              const inviteState = inviteStates[assignment.id]
              return (
                <li key={assignment.id} className="flex items-center justify-between gap-3 px-4 py-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium text-gray-800">{assignmentLabel(assignment)}</p>
                      {assignment.accepted ? (
                        <Badge color="green" testId={`owner-invite-status-${assignment.id}`}>Active</Badge>
                      ) : assignment.invited ? (
                        <Badge color="amber" testId={`owner-invite-status-${assignment.id}`}>Invited</Badge>
                      ) : (
                        <Badge color="gray" testId={`owner-invite-status-${assignment.id}`}>Not invited</Badge>
                      )}
                    </div>
                    {assignment.notes && <p className="text-xs text-gray-500 mt-0.5">{assignment.notes}</p>}
                    {inviteState?.message && (
                      <p className="text-xs text-green-600 mt-1 break-all" data-testid={`owner-invite-message-${assignment.id}`}>
                        {inviteState.message}
                      </p>
                    )}
                    {inviteState?.error && (
                      <p className="text-xs text-red-600 mt-1" data-testid={`owner-invite-error-${assignment.id}`}>
                        {inviteState.error}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {onInvite && !assignment.accepted && (
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={inviteState?.sending}
                        onClick={() => handleInvite(assignment)}
                        testId="owner-assignment-invite"
                      >
                        {assignment.invited ? 'Resend setup email' : 'Send setup email'}
                      </Button>
                    )}
                    {onRemove && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onRemove(assignment.id)}
                        testId="owner-assignment-remove"
                      >
                        Remove
                      </Button>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
