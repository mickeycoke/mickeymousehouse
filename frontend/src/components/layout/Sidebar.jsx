import { useEffect, useState } from 'react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { useOperatingStudio } from '../../context/StudioContext'
import { listMyBillingStudios } from '../../api/ownerBilling'
import { APP_NAME } from '../../config/brand'
import {
  IconHome,
  IconUsers,
  IconSettings,
  IconBuildingCommunity,
  IconLogout,
  IconActivity,
  IconHelp,
  IconMessage,
  IconMessageQuestion,
  IconCreditCard,
} from '@tabler/icons-react'

// adminOnly items are hidden for non-admin logins (their pages would just
// bounce them back to Home).
// Order is the drill-down flow: Franchise → Studios →
// people, then everything else.
const navItems = [
  { label: 'Home', to: '/admin/overview', testId: 'sidebar-nav-home', Icon: IconHome },
  // Announcements sit near the top — they're the first thing to read, and
  // the Questions inbox (admin) sits right under it so replies aren't missed.
  // `everyone` bypasses every role filter below: a broadcast is for all logins,
  // and its reply channel has to be reachable by whoever received it.
  { label: 'Notes to users', to: '/notes', testId: 'sidebar-nav-notes', Icon: IconMessage, everyone: true },
  { label: 'Chat with us', to: '/chat', testId: 'sidebar-nav-chat', Icon: IconMessageQuestion, everyone: true },
  { label: 'Questions', to: '/admin/questions', testId: 'sidebar-nav-questions', Icon: IconMessageQuestion, adminOnly: true },
  { label: 'Franchise', to: '/ownership/franchises', testId: 'sidebar-nav-franchise', Icon: IconBuildingCommunity, adminOnly: true },
  { label: 'Studios', to: '/studios',        testId: 'sidebar-nav-studios',   Icon: IconBuildingCommunity, franchiseManager: true },
  // Studio owners/managers' discoverable entry point to the onboarding +
  // shared front-desk device links (previously buried in Profile).
  { label: 'Studio Manager', to: '/studio-manager', testId: 'sidebar-nav-studio-manager', Icon: IconBuildingCommunity, studioManagerTab: true },
  // Self-serve owner Billing tab — separate from the admin's central roster.
  // Owner-level only (studio_owner or franchise_owner_level), never a
  // manager — billing is a financial decision, not an operational one.
  { label: 'Billing', to: '/billing', testId: 'sidebar-nav-billing', Icon: IconCreditCard, ownerBillingTab: true },
  { label: 'Manage', to: '/setup', testId: 'sidebar-nav-setup', Icon: IconSettings },
  // Franchise reporting-owner: add + invite reporting users into their franchise.
  { label: 'Franchise Users', to: '/franchise/users', testId: 'sidebar-nav-franchise-users', Icon: IconUsers, reportingOwner: true },
  // How-to guides for admins + studio/franchise owners
  { label: 'Help', to: '/help', testId: 'sidebar-nav-help', Icon: IconHelp, staffHelp: true },
  // "Users" is an ADMIN concept — everyone else thinks in instructors
  { label: 'Users',   to: '/admin/users',    testId: 'sidebar-nav-users',    Icon: IconUsers, adminOnly: true },
  { label: 'Studio assignment', to: '/admin/studio-assignment', testId: 'sidebar-nav-studio-assignment', Icon: IconBuildingCommunity, adminOnly: true },
  // Admin: audit log of every sign-in across all studios
  { label: 'Login log', to: '/admin/login-log', testId: 'sidebar-nav-login-log', Icon: IconActivity, adminOnly: true },
]

// onNavigate: optional callback fired after any nav action — the mobile
// drawer passes it to close itself when a link is tapped.
export default function Sidebar({ onNavigate }) {
  const { user, myRoles, logout } = useAuth()
  const { studio: operatingStudio, setStudio, clearStudio } = useOperatingStudio()
  const myStudios = myRoles?.studios ?? []
  const navigate = useNavigate()
  const location = useLocation()

  // Billing tab: only shown when the backend returns at least one billing
  // row — i.e. the admin has set an amount AND sent the checkout email (or a
  // subscription already exists). The backend enforces this filter; an empty
  // list means no tab at all, so a studio owner who hasn't been invited to
  // billing never sees a Billing surface.
  // Dot: red if ANY visible studio isn't active, green if every one is.
  const mayOwnBilling = (myRoles?.studio_owner || myRoles?.franchise_owner_level) && user?.role !== 'admin'
  const [billingRows, setBillingRows] = useState(0)
  const [billingDot, setBillingDot] = useState(null)
  useEffect(() => {
    if (!mayOwnBilling) { setBillingRows(0); setBillingDot(null); return }
    let cancelled = false
    listMyBillingStudios()
      .then((rows) => {
        if (cancelled) return
        setBillingRows(rows.length)
        if (rows.length === 0) { setBillingDot(null); return }
        setBillingDot(rows.every((r) => r.status === 'active') ? 'green' : 'red')
      })
      .catch(() => { if (!cancelled) { setBillingRows(0); setBillingDot(null) } })
    return () => { cancelled = true }
  }, [mayOwnBilling])

  // Multi-studio staff pick their working studio here (a second, always-visible
  // way to switch — the header carries the same control). Selecting one scopes
  // the whole app to it; reload so every screen refetches at the new scope.
  function switchStudio(id) {
    const s = myStudios.find((x) => x.id === id)
    if (s) setStudio({ id: s.id, name: s.name }); else clearStudio()
    onNavigate?.()
    window.location.href = '/admin/overview'
  }

  // Users and Instructors share a pathname and differ only by query string,
  // so NavLink's default isActive would highlight both at once.
  function isItemActive(to, isActive) {
    if (!to.includes('?')) return isActive && !(to === '/admin/users' && location.search.includes('role='))
    const [path, query] = to.split('?')
    return location.pathname === path && location.search.includes(query)
  }

  async function handleLogout() {
    await logout()
    onNavigate?.()
    navigate('/login')
  }

  return (
    <aside className="w-64 bg-white border-r border-gray-200 flex flex-col h-full flex-shrink-0">
      {/* Brand + studio */}
      <div className="flex shrink-0 items-center gap-2.5 border-b border-gray-200 px-5 py-4">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white">
          <IconActivity size={18} />
        </span>
        <span className="min-w-0 truncate text-[15px] font-semibold text-gray-900" data-testid="sidebar-app-title">
          {myRoles?.studio_name || APP_NAME}
        </span>
      </div>

      {/* Multi-studio staff: choose which studio you're working in. */}
      {myStudios.length > 1 && (
        <div className="border-b border-gray-200 px-3 py-3" data-testid="sidebar-studio-switcher">
          <label htmlFor="sidebar-studio-select"
            className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-gray-400">
            Working in
          </label>
          <select
            id="sidebar-studio-select"
            data-testid="sidebar-studio-select"
            value={operatingStudio?.id || ''}
            onChange={(e) => switchStudio(e.target.value)}
            className="w-full truncate rounded-lg border border-gray-300 bg-white py-1.5 pl-2 pr-7 text-sm font-medium text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All my studios</option>
            {myStudios.map((s) => (
              <option key={s.id} value={s.id}>{s.name}{s.is_primary ? ' ★' : ''}</option>
            ))}
          </select>
        </div>
      )}

      {/* Navigation — scrolls on its own when the list is taller than the
          viewport (mobile drawer especially). min-h-0 lets this flex child
          shrink below its content so overflow-y-auto actually engages; without
          it the nav would push the sign-out button off the bottom of the phone. */}
      <nav className="min-h-0 flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {navItems
          .filter((item) => {
            // Announcements + their reply channel reach every signed-in user.
            if (item.everyone) return true
            // Franchise reporting persona: Home always; Franchise Users only
            // for OWNERS (reports-only users are view-only).
            if (myRoles?.franchise_reporting_only) {
              if (item.to === '/admin/overview') return true
              if (item.to === '/franchise/users') return !!myRoles.franchise_can_invite
              return false
            }
            if (item.reportingOwner) return false   // the Franchise Users item is persona-only
            // Scoped to one operating studio: hide franchise-wide entries — the
            // Franchise section (management + franchise reports) spans studios.
            if (operatingStudio && item.to === '/ownership/franchises') return false
            if (item.adminOnly) return user?.role === 'admin'
            // Help guides: admins + studio owners/managers + franchise managers.
            if (item.staffHelp) return user?.role === 'admin' || myRoles?.can_manage_users || myRoles?.franchise_manager
            if (item.userAdmin) return user?.role === 'admin' || myRoles?.can_manage_users
            if (item.franchiseManager) return user?.role === 'admin' || myRoles?.franchise_manager
            // Same gate ProfilePage.jsx already uses for this content: studio
            // owners/managers, but not admins (admins use the Studios page).
            if (item.studioManagerTab) return (myRoles?.studio_owner || myRoles?.studio_manager) && user?.role !== 'admin'
            if (item.ownerBillingTab) return mayOwnBilling && billingRows > 0
            return true
          })
          .map(({ label, to, testId, Icon, ownerBillingTab }) => (
          <NavLink
            key={to}
            to={to}
            data-testid={testId}
            onClick={() => onNavigate?.()}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 text-sm rounded-lg transition-colors ${
                isItemActive(to, isActive)
                  ? 'bg-blue-50 text-blue-700 font-medium'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              }`
            }
          >
            <Icon size={16} aria-hidden="true" />
            {label}
            {ownerBillingTab && billingDot && (
              <span
                data-testid="sidebar-billing-dot"
                data-status={billingDot}
                className={`ml-auto h-2 w-2 shrink-0 rounded-full ${billingDot === 'green' ? 'bg-green-500' : 'bg-red-500'}`}
              />
            )}
          </NavLink>
        ))}
      </nav>

      {/* User info + logout — pinned below the scrolling nav, never pushed off */}
      <div className="shrink-0 px-3 py-4 border-t border-gray-200">
        {user && (
          <NavLink
            to="/profile"
            onClick={() => onNavigate?.()}
            data-testid="sidebar-profile-link"
            className="mb-2 block rounded-lg px-3 py-1.5 hover:bg-gray-50"
            title="Profile & password"
          >
            <p className="text-sm font-medium text-gray-900 truncate">{user.name}</p>
            <p className="text-xs text-gray-500 capitalize">{myRoles?.studio_name ? `${user.role} · ${myRoles.studio_name}` : user.role}</p>
          </NavLink>
        )}
        <button
          onClick={handleLogout}
          data-testid="sidebar-logout-button"
          className="w-full flex items-center gap-3 px-3 py-2 text-sm text-gray-600 rounded-lg hover:bg-gray-50 hover:text-gray-900 transition-colors"
        >
          <IconLogout size={16} aria-hidden="true" />
          Sign out
        </button>
      </div>
    </aside>
  )
}
