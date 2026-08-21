import { Link } from 'react-router-dom'
import AppShell from '../../components/layout/AppShell'
import OwnershipPageShell from '../../components/ownership/OwnershipPageShell'
import OwnershipVisibilityBadge from '../../components/ownership/OwnershipVisibilityBadge'
import { OwnershipError, OwnershipLoading } from '../../components/ownership/OwnershipStates'
import Button from '../../components/ui/Button'
import { useOwnershipScope } from '../../hooks/useOwnershipScope'

const OWNERSHIP_AREAS = [
  {
    title: 'Studio Owners',
    description: 'Assign and remove owners for individual studios.',
    to: '/ownership/studio-owners',
    testId: 'ownership-dashboard-studio-owners',
  },
  {
    title: 'Franchises',
    description: 'Create, edit, and deactivate franchise records.',
    to: '/ownership/franchises',
    testId: 'ownership-dashboard-franchises',
  },
  {
    title: 'Franchise Owners',
    description: 'Assign and remove owners for franchise-level access.',
    to: '/ownership/franchise-owners',
    testId: 'ownership-dashboard-franchise-owners',
  },
  {
    title: 'Franchise Studios',
    description: 'Connect studios to franchise ownership groups.',
    to: '/ownership/franchise-studios',
    testId: 'ownership-dashboard-franchise-studios',
  },
  {
    title: 'My Scope',
    description: 'View your current ownership access and visible studios.',
    to: '/ownership/scope',
    testId: 'ownership-dashboard-scope',
  },
]

export default function OwnershipDashboardPage() {
  const { scope, loading, error, refetch } = useOwnershipScope()

  return (
    <AppShell>
      <OwnershipPageShell
        title="Ownership"
        subtitle="Studio and franchise ownership setup"
        actions={<OwnershipVisibilityBadge scope={scope} />}
      >
        {loading && <OwnershipLoading />}
        {!loading && error && <OwnershipError message={error} onRetry={refetch} />}
        {!loading && !error && (
          <div className="grid gap-4 md:grid-cols-2" data-testid="ownership-dashboard">
            {OWNERSHIP_AREAS.map((area) => (
              <section key={area.to} className="rounded-lg border border-gray-200 bg-white px-5 py-4">
                <h2 className="text-base font-semibold text-gray-900">{area.title}</h2>
                <p className="mt-1 text-sm text-gray-500">{area.description}</p>
                <Link to={area.to} className="mt-4 inline-block" data-testid={area.testId}>
                  <Button size="sm" variant="secondary">Open</Button>
                </Link>
              </section>
            ))}
          </div>
        )}
      </OwnershipPageShell>
    </AppShell>
  )
}
