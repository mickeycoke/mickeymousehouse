import { useNavigate } from 'react-router-dom'
import AppShell from '../../components/layout/AppShell'
import SetupPageShell from '../../components/setup/SetupPageShell'
import { useAuth } from '../../context/AuthContext'

// Manage is grouped into sections. Each card carries `group` and a
// `requires` visibility gate:
//   'all'   — everyone who reaches Manage
//   'staff' — admins + anyone who manages a studio's users
//   'admin' — platform admins only (cross-studio / platform surfaces)
const CARDS = [
  // ── Studio ──────────────────────────────────────────────────────────────
  { group: 'Studio', requires: 'staff', label: 'Instructors', description: 'Add, edit, and manage the instructors on your team.', to: '/admin/users?role=instructor', testId: 'setup-nav-instructors' },
  // ── Billing ─────────────────────────────────────────────────────────────
  { group: 'Billing', requires: 'admin', label: 'Billing', description: 'Studio subscriptions — set a contracted price and send a Stripe checkout link.', to: '/setup/billing', testId: 'setup-nav-billing' },
  { group: 'Billing', requires: 'admin', label: 'Pricing tiers', description: 'The price book — Free through Enterprise, with a live $/client-at-cap.', to: '/setup/pricing-tiers', testId: 'setup-nav-pricing-tiers' },
]

const GROUP_ORDER = ['Studio', 'Billing']

export default function SetupDashboardPage() {
  const navigate = useNavigate()
  const { isAdmin, myRoles } = useAuth()
  const canManageUsers = isAdmin || !!myRoles?.can_manage_users

  const canSee = (requires) =>
    requires === 'all' || (requires === 'staff' && canManageUsers) || (requires === 'admin' && isAdmin)

  const groups = GROUP_ORDER
    .map((name) => ({ name, cards: CARDS.filter((c) => c.group === name && canSee(c.requires)) }))
    .filter((g) => g.cards.length > 0)

  return (
    <AppShell>
      <SetupPageShell title="Manage" subtitle="Manage operational data for the studio">
        <div className="max-w-2xl space-y-8" data-testid="setup-dashboard">
          {groups.map((group) => (
            <section key={group.name} data-testid={`setup-group-${group.name.toLowerCase()}`}>
              <div className="mb-3 flex items-center gap-3">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400">{group.name}</h2>
                <div className="h-px flex-1 bg-gray-200" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                {group.cards.map((s) => (
                  <button
                    key={s.to}
                    data-testid={s.testId}
                    onClick={() => navigate(s.to)}
                    className="rounded-xl border border-gray-200 bg-white px-6 py-5 text-left transition-colors hover:border-blue-300 hover:bg-blue-50"
                  >
                    <p className="mb-1 font-semibold text-gray-900">{s.label}</p>
                    <p className="text-sm text-gray-500">{s.description}</p>
                  </button>
                ))}
              </div>
            </section>
          ))}
        </div>
      </SetupPageShell>
    </AppShell>
  )
}
