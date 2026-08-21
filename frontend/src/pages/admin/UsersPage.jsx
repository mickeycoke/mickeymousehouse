import { useState, useEffect } from 'react'
import AppShell from '../../components/layout/AppShell'
import PageHeader from '../../components/layout/PageHeader'
import DataTable from '../../components/ui/DataTable'
import Badge from '../../components/ui/Badge'
import Button from '../../components/ui/Button'
import Modal from '../../components/ui/Modal'
import Input from '../../components/ui/Input'
import { useUsers } from '../../hooks/useUsers'
import { useAuth } from '../../context/AuthContext'
import { impersonateApi, sendInvite, getSetupLink } from '../../api/auth'
import { getRolesSummary } from '../../api/roles'
import { getStudios } from '../../api/ownership'
import { TIMEZONES } from '../../utils/time'
import RolesEditor from '../../components/admin/RolesEditor'
import InstructorPinModal from '../../components/admin/InstructorPinModal'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { createUser, updateUser, deleteUser } from '../../api/users'
import { getApiErrorMessage } from '../../utils/apiError'

const ROLE_COLOR = { admin: 'purple', manager: 'blue', instructor: 'gray', member: 'gray' }

const EMPTY_FORM = { name: '', email: '', password: '', role: 'instructor', timezone: '', studioId: '' }

// Mirrors SCOPED_ASSIGNABLE_ROLES in backend/app/routes/users.py — the roles a
// studio owner/manager may act on. Used only to avoid offering a button the
// server would refuse; the server remains the authority.
const SETUP_LINK_ROLES = new Set(['instructor', 'member'])

export default function UsersPage() {
  const { users, loading, refetch } = useUsers()
  const { user: currentUser, isAdmin, impersonate } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  // ?role=instructor turns this into the Instructors page (same screen, filtered)
  const roleFilter = searchParams.get('role')
  const [roleSelect, setRoleSelect] = useState(roleFilter || '')
  const [studioFilter, setStudioFilter] = useState('')   // '' = all, '__has'/'__none', or a studio id
  const [emailFilter, setEmailFilter] = useState('')     // '' = all, 'has', 'none'
  const [studios, setStudios] = useState([])
  const [formStudios, setFormStudios] = useState([])  // all studios, for the form's Primary studio picker
  const [roleHats, setRoleHats] = useState({})
  const [search, setSearch] = useState('')
  const [optionsUser, setOptionsUser] = useState(null)  // tapped user (mobile options sheet)
  const [rolesUser, setRolesUser] = useState(null)  // user whose roles are being edited
  const [pinUser, setPinUser] = useState(null)      // instructor whose shared-device PIN is open
  const [notice, setNotice] = useState(null)  // {kind:'ok'|'err', text, link} from the setup actions
  const [linkCopied, setLinkCopied] = useState(false)

  // Email this user a magic link to set their own password (Phase 0 invite).
  async function handleSendSetup(u) {
    try {
      const res = await sendInvite(u.id)
      setNotice({ kind: 'ok', text: res?.invite_link
        ? `Setup email sent to ${u.email}. Dev link: ${res.invite_link}`
        : `Setup email sent to ${u.email}.` })
    } catch (err) {
      setNotice({ kind: 'err', text: getApiErrorMessage(err, 'Could not send setup email') })
    }
  }

  // The same magic link, handed over instead of emailed. Email is a single
  // point of failure for the ONLY self-service way back into an account: if
  // the mail host started rejecting the app's login there would be no way
  // to get anyone a password without a server shell. Read it out,
  // text it, or hand it over at the desk — they still choose their own
  // password, so nobody has to know it.
  async function handleCopySetupLink(u) {
    setLinkCopied(false)
    try {
      const res = await getSetupLink(u.id)
      // Best-effort: clipboard needs a secure context and can be denied, and
      // the link is useless if a failed copy is the only way to see it — so it
      // is always rendered in the notice too.
      try {
        await navigator.clipboard.writeText(res.link)
        setLinkCopied(true)
      } catch { /* shown below regardless */ }
      setNotice({
        kind: 'ok',
        text: `Setup link for ${res.name} (${res.email}) — good for ${res.expires_in_hours} hours, and it stops working the moment they use it.`,
        link: res.link,
      })
    } catch (err) {
      setNotice({ kind: 'err', text: getApiErrorMessage(err, 'Could not create a setup link') })
    }
  }

  // Full role picture (hats) per user, e.g. studio owner + instructor
  useEffect(() => {
    getRolesSummary()
      .then((rows) => {
        const map = {}
        rows.forEach((r) => { map[r.user_id] = r })
        setRoleHats(map)
      })
      .catch(() => setRoleHats({}))
  }, [users])

  async function handleImpersonate(target) {
    try {
      const data = await impersonateApi(target.id)
      impersonate(data.user, data.access_token)
      navigate('/admin/overview')
    } catch {
      setError('Could not impersonate this user')
    }
  }
  const [modal, setModal] = useState({ type: null, user: null })
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  function openAdd() {
    setForm(EMPTY_FORM)
    setError('')
    setModal({ type: 'add', user: null })
  }

  function openEdit(user) {
    setForm({ name: user.name, email: user.email || '', password: '', role: user.role, timezone: user.timezone || '', studioId: user.studio_id || '' })
    setError('')
    setModal({ type: 'edit', user })
  }

  function openDelete(user) {
    setModal({ type: 'delete', user })
  }

  function closeModal() {
    setModal({ type: null, user: null })
  }

  function handleChange(e) {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }))
  }

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      // Email is optional (PIN-only instructors). Omit it when blank so it stays
      // NULL rather than an empty string that would collide on the unique index.
      const emailVal = (form.email || '').trim()
      const payload = { name: form.name, role: form.role, timezone: form.timezone || null, studio_id: form.studioId || null }
      if (emailVal) payload.email = emailVal
      if (form.password) payload.password = form.password
      if (modal.type === 'add') {
        await createUser(payload)
      } else {
        await updateUser(modal.user.id, payload)
      }
      await refetch()
      closeModal()
    } catch (err) {
      setError(getApiErrorMessage(err, 'Save failed'))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    setSaving(true)
    try {
      await deleteUser(modal.user.id)
      await refetch()
      closeModal()
    } catch (err) {
      setError(getApiErrorMessage(err, 'Delete failed'))
    } finally {
      setSaving(false)
    }
  }

  useEffect(() => {
    getStudios().then(setStudios).catch(() => setStudios([]))
    // Every studio, for the "Primary studio" picker in the add/edit form, so you
    // can set any instructor's home studio regardless of the current scope.
    getStudios({ allStudios: true }).then(setFormStudios).catch(() => setFormStudios([]))
  }, [])
  useEffect(() => { setRoleSelect(roleFilter || '') }, [roleFilter])

  const studioName = studios.find((st) => st.id === studioFilter)
  const studioLabel = studioName ? (studioName.display_name || studioName.name) : null

  // Does a user "belong" to ANY studio at all — home studio, owner/manager
  // hat, or instructor membership? Mirrors the studio-less backlog
  // definition so "No studio" here == what shows there.
  function hasAnyStudio(u) {
    const hats = roleHats[u.id]
    return Boolean(u.studio_id)
      || (hats?.studio_owner_of ?? []).length > 0
      || (hats?.studio_manager_of ?? []).length > 0
      || (hats?.instructor_studio_ids ?? []).length > 0
  }

  // Studio filter: '' = all, '__has'/'__none' = any/no studio, else a specific
  // studio (matched via home studio, owner/manager hat, or instructor
  // membership at that studio).
  function inStudio(u) {
    if (!studioFilter) return true
    if (studioFilter === '__has') return hasAnyStudio(u)
    if (studioFilter === '__none') return !hasAnyStudio(u)
    if (u.studio_id === studioFilter) return true
    const hats = roleHats[u.id]
    if (!hats) return false
    if ((hats.instructor_studio_ids ?? []).includes(studioFilter)) return true
    const names = [
      ...(hats.studio_owner_of ?? []),
      ...(hats.studio_manager_of ?? []),
    ]
    return studioLabel ? names.includes(studioLabel) : false
  }

  const filteredUsers = users.filter((u) => {
    if (roleSelect === 'instructor' && u.role !== 'instructor') return false
    if (roleSelect === 'admin' && u.role !== 'admin') return false
    if (!inStudio(u)) return false
    const hasEmail = Boolean((u.email || '').trim())
    if (emailFilter === 'has' && !hasEmail) return false
    if (emailFilter === 'none' && hasEmail) return false
    const term = search.trim().toLowerCase()
    if (!term) return true
    return u.name.toLowerCase().includes(term) || (u.email || '').toLowerCase().includes(term)
  })

  const columns = [
    { accessorKey: 'name', header: 'Name' },
    { accessorKey: 'email', header: 'Email' },
    {
      accessorKey: 'role',
      header: 'Roles',
      cell: ({ row }) => {
        const hats = roleHats[row.original.id]
        return (
          <div className="flex flex-wrap gap-1" data-testid="user-role-hats">
            <Badge color={ROLE_COLOR[row.original.role] || 'gray'}>
              {row.original.role}
            </Badge>
            {(hats?.studio_owner_of ?? []).map((name) => (
              <Badge key={`so-${name}`} color="green">studio owner · {name}</Badge>
            ))}
            {(hats?.studio_manager_of ?? []).map((name) => (
              <Badge key={`sm-${name}`} color="blue">studio manager · {name}</Badge>
            ))}
            {(hats?.franchise_owner_of ?? []).map((name) => (
              <Badge key={`fo-${name}`} color="amber">franchise owner · {name}</Badge>
            ))}
            {(hats?.franchise_manager_of ?? []).map((name) => (
              <Badge key={`fm-${name}`} color="amber">franchise manager · {name}</Badge>
            ))}
            {(hats?.franchise_reports_of ?? []).map((name) => (
              <Badge key={`fr-${name}`} color="amber">franchise reports · {name}</Badge>
            ))}
          </div>
        )
      },
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="flex gap-2 justify-end">
          {row.original.email && (
            <Button
              size="sm"
              variant="ghost"
              testId="users-invite-button"
              onClick={() => handleSendSetup(row.original)}
            >
              Send setup email
            </Button>
          )}
          {/* Offered only where the API will actually allow it. The backend gate
              (`_require_target_in_scope`) restricts a non-admin to instructors
              and members, so showing this to a studio owner on an admin's or
              manager's row advertises a capability that will 403 — the UI
              should not write cheques the server refuses. Non-admins only ever
              see their own studios' rows in this list, so the role check is the
              only part that needs mirroring here. */}
          {row.original.email && (isAdmin || SETUP_LINK_ROLES.has(row.original.role)) && (
            <Button
              size="sm"
              variant="ghost"
              testId="users-setup-link-button"
              onClick={() => handleCopySetupLink(row.original)}
            >
              Copy setup link
            </Button>
          )}
          {isAdmin && row.original.id !== currentUser?.id && (
            <Button
              size="sm"
              variant="ghost"
              testId="users-impersonate-button"
              onClick={() => handleImpersonate(row.original)}
            >
              Impersonate
            </Button>
          )}
          {row.original.role === 'instructor' && (
            <Button
              size="sm"
              variant="secondary"
              testId="users-pin-button"
              onClick={() => setPinUser(row.original)}
            >
              PIN
            </Button>
          )}
          <Button
            size="sm"
            variant="secondary"
            testId="users-edit-button"
            onClick={() => openEdit(row.original)}
          >
            Edit
          </Button>
          <Button
            size="sm"
            variant="danger"
            testId="users-delete-button"
            onClick={() => openDelete(row.original)}
          >
            Delete
          </Button>
        </div>
      ),
    },
  ]

  return (
    <AppShell>
      <PageHeader
        title={roleFilter === 'instructor' ? 'Instructors' : 'Users'}
        subtitle={`${filteredUsers.length} ${roleFilter === 'instructor' ? 'instructor' : 'user'}${filteredUsers.length !== 1 ? 's' : ''}`}
        action={
          <Button testId="users-add-button" onClick={openAdd}>
            Add user
          </Button>
        }
      />

      <div className="px-4 py-4 sm:px-8">
        {notice && (
          <div
            data-testid="users-invite-notice"
            className={`mb-3 rounded-lg border px-3 py-2 text-sm ${notice.kind === 'ok'
              ? 'border-green-200 bg-green-50 text-green-800'
              : 'border-red-200 bg-red-50 text-red-700'}`}
          >
            <div className="flex items-start justify-between gap-3">
              <span className="min-w-0 break-words">{notice.text}</span>
              <button onClick={() => setNotice(null)} className="shrink-0 text-xs underline">dismiss</button>
            </div>
            {notice.link && (
              <div className="mt-2 flex items-center gap-2">
                <input
                  readOnly
                  value={notice.link}
                  data-testid="users-setup-link-value"
                  onFocus={(e) => e.target.select()}
                  className="min-w-0 flex-1 truncate rounded border border-green-300 bg-white px-2 py-1 font-mono text-xs text-gray-700"
                />
                <button
                  type="button"
                  data-testid="users-setup-link-copy"
                  onClick={() => navigator.clipboard?.writeText(notice.link)
                    .then(() => setLinkCopied(true)).catch(() => {})}
                  className="shrink-0 rounded border border-green-300 bg-white px-2 py-1 text-xs font-medium"
                >
                  {linkCopied ? 'Copied' : 'Copy'}
                </button>
              </div>
            )}
          </div>
        )}
        <div className="mb-4 flex flex-col gap-2 sm:max-w-3xl sm:flex-row sm:flex-wrap">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search users by name or email…"
            data-testid="users-search-input"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 sm:flex-1"
          />
          {/* Only show a role picker on the full Users page (Instructors is pre-filtered) */}
          {roleFilter !== 'instructor' && (
            <select
              value={roleSelect}
              onChange={(e) => setRoleSelect(e.target.value)}
              data-testid="users-role-filter"
              className="rounded-lg border border-gray-300 px-2 py-2 text-sm"
            >
              <option value="">All roles</option>
              <option value="instructor">Instructors</option>
              <option value="admin">Admins</option>
            </select>
          )}
          <select
            value={emailFilter}
            onChange={(e) => setEmailFilter(e.target.value)}
            data-testid="users-email-filter"
            className="rounded-lg border border-gray-300 px-2 py-2 text-sm"
          >
            <option value="">Any email</option>
            <option value="has">Has an email</option>
            <option value="none">No email</option>
          </select>
          <select
            value={studioFilter}
            onChange={(e) => setStudioFilter(e.target.value)}
            data-testid="users-studio-filter"
            className="rounded-lg border border-gray-300 px-2 py-2 text-sm"
          >
            <option value="">All studios</option>
            <option value="__has">In a studio</option>
            <option value="__none">Not in a studio</option>
            <optgroup label="Specific studio">
              {studios.map((st) => (
                <option key={st.id} value={st.id}>{st.display_name || st.name}</option>
              ))}
            </optgroup>
          </select>
        </div>

        {/* Phone: tappable cards — tap a user to see options */}
        <div className="space-y-2 md:hidden">
          {filteredUsers.map((u) => {
            const hats = roleHats[u.id]
            return (
              <button
                key={u.id}
                type="button"
                data-testid="users-card"
                onClick={() => setOptionsUser(u)}
                className="w-full rounded-lg border border-gray-200 bg-white px-4 py-3 text-left"
              >
                <p className="text-sm font-semibold text-gray-900">{u.name}</p>
                <p className="text-xs text-gray-500">{u.email}</p>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  <Badge color={ROLE_COLOR[u.role] || 'gray'}>{u.role}</Badge>
                  {(hats?.studio_owner_of ?? []).map((n) => <Badge key={n} color="green">studio owner</Badge>)}
                  {(hats?.studio_manager_of ?? []).map((n) => <Badge key={n} color="blue">studio manager</Badge>)}
                  {(hats?.franchise_owner_of ?? []).map((n) => <Badge key={n} color="amber">franchise owner</Badge>)}
                  {(hats?.franchise_manager_of ?? []).map((n) => <Badge key={n} color="amber">franchise manager</Badge>)}
                  {(hats?.franchise_reports_of ?? []).map((n) => <Badge key={n} color="amber">franchise reports</Badge>)}
                </div>
              </button>
            )
          })}
          {filteredUsers.length === 0 && (
            <p className="text-sm text-gray-500">No users match.</p>
          )}
        </div>

        <div className="hidden md:block">
        <DataTable
          columns={columns}
          data={filteredUsers}
          isLoading={loading}
          testId="users-table"
          rowTestId="id"
          emptyMessage="No users found"
        />
        </div>
      </div>

      {/* Mobile options sheet: tap a user, choose an action */}
      <Modal
        isOpen={!!optionsUser}
        onClose={() => setOptionsUser(null)}
        title={optionsUser?.name ?? ''}
      >
        <p className="mb-4 text-sm text-gray-500">{optionsUser?.email}</p>
        <div className="flex flex-col gap-2" data-testid="user-options">
          <Button testId="user-option-edit" variant="secondary"
            onClick={() => { const u = optionsUser; setOptionsUser(null); openEdit(u) }}>
            Edit user
          </Button>
          {optionsUser?.role === 'instructor' && (
            <Button testId="user-option-pin" variant="secondary"
              onClick={() => { const u = optionsUser; setOptionsUser(null); setPinUser(u) }}>
              Shared-device PIN
            </Button>
          )}
          {isAdmin && (
            <Button testId="user-option-roles" variant="secondary"
              onClick={() => { const u = optionsUser; setOptionsUser(null); setRolesUser(u) }}>
              Manage roles
            </Button>
          )}
          {isAdmin && optionsUser?.id !== currentUser?.id && (
            <Button testId="user-option-impersonate" variant="secondary"
              onClick={() => { const u = optionsUser; setOptionsUser(null); handleImpersonate(u) }}>
              Impersonate (act as this user)
            </Button>
          )}
          <Button testId="user-option-delete" variant="danger"
            onClick={() => { const u = optionsUser; setOptionsUser(null); openDelete(u) }}>
            Deactivate user
          </Button>
        </div>
      </Modal>

      <RolesEditor
        user={rolesUser}
        hats={rolesUser ? roleHats[rolesUser.id] : null}
        isOpen={!!rolesUser}
        onClose={() => setRolesUser(null)}
        onSaved={() => { refetch(); getRolesSummary().then((rows) => { const m = {}; rows.forEach((r) => { m[r.user_id] = r }); setRoleHats(m) }).catch(() => {}) }}
      />

      <InstructorPinModal instructor={pinUser} onClose={() => setPinUser(null)} />

      {/* Add / Edit modal */}
      <Modal
        isOpen={modal.type === 'add' || modal.type === 'edit'}
        onClose={closeModal}
        title={modal.type === 'add' ? 'Add user' : 'Edit user'}
      >
        <form onSubmit={handleSave} className="space-y-4">
          <Input
            id="name"
            label="Name"
            name="name"
            value={form.name}
            onChange={handleChange}
            testId="user-form-name-input"
            required
          />
          <Input
            id="email"
            label="Email (optional — leave blank for PIN-only instructors)"
            name="email"
            type="email"
            value={form.email}
            onChange={handleChange}
            testId="user-form-email-input"
          />
          <Input
            id="password"
            label={modal.type === 'edit'
              ? 'New password (leave blank to keep)'
              : 'Password (optional — leave blank, then use “Send setup email”)'}
            name="password"
            type="password"
            value={form.password}
            onChange={handleChange}
            testId="user-form-password-input"
          />
          {roleFilter !== 'instructor' && (<div>
            <label htmlFor="role" className="block text-sm font-medium text-gray-700 mb-1">
              Role
            </label>
            <select
              id="role"
              name="role"
              value={form.role}
              onChange={handleChange}
              data-testid="user-form-role-select"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="instructor">Instructor</option>
              {isAdmin && <option value="manager">Manager</option>}
              {isAdmin && <option value="admin">Admin</option>}
              <option value="member">Member — standard login (franchise/studio roles are granted separately)</option>
            </select>
          </div>)}
          <div>
            <label htmlFor="user-studio" className="block text-sm font-medium text-gray-700 mb-1">
              Primary studio
              <span className="ml-1 text-xs font-normal text-gray-400">(home studio — required for shared-device PIN sign-in)</span>
            </label>
            <select
              id="user-studio"
              value={form.studioId}
              onChange={(e) => setForm((f) => ({ ...f, studioId: e.target.value }))}
              data-testid="user-form-studio-select"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">— no studio —</option>
              {formStudios.map((s) => (
                <option key={s.id} value={s.id}>{s.display_name || s.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Local time zone</label>
            <select
              value={form.timezone}
              onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}
              data-testid="user-form-timezone-select"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            >
              <option value="">Use the studio time zone</option>
              {TIMEZONES.map((z) => <option key={z} value={z}>{z}</option>)}
            </select>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex justify-end gap-3 pt-2">
            <Button type="button" variant="secondary" testId="user-form-cancel-button" onClick={closeModal}>
              Cancel
            </Button>
            <Button type="submit" loading={saving} testId="user-form-submit-button">
              {modal.type === 'add' ? 'Create user' : 'Save changes'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Delete confirm modal */}
      <Modal
        isOpen={modal.type === 'delete'}
        onClose={closeModal}
        title="Delete user"
      >
        <p className="text-sm text-gray-600 mb-6">
          Are you sure you want to delete <strong>{modal.user?.name}</strong>? This action deactivates the account.
        </p>
        {error && <p className="text-sm text-red-600 mb-4">{error}</p>}
        <div className="flex justify-end gap-3">
          <Button variant="secondary" testId="delete-cancel-button" onClick={closeModal}>
            Cancel
          </Button>
          <Button variant="danger" loading={saving} testId="delete-confirm-button" onClick={handleDelete}>
            Delete
          </Button>
        </div>
      </Modal>
    </AppShell>
  )
}
