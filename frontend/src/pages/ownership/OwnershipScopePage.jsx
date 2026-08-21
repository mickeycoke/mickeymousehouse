import AppShell from '../../components/layout/AppShell'
import OwnershipPageShell from '../../components/ownership/OwnershipPageShell'
import OwnershipVisibilityBadge from '../../components/ownership/OwnershipVisibilityBadge'
import { OwnershipLoading, OwnershipError } from '../../components/ownership/OwnershipStates'
import { useOwnershipScope, useVisibleStudios } from '../../hooks/useOwnershipScope'

function ScopeSection({ title, items, emptyText, testId }) {
  return (
    <section className="rounded-lg border border-gray-200 bg-white px-5 py-4" data-testid={testId}>
      <h2 className="text-sm font-semibold text-gray-700 mb-3">{title}</h2>
      {items.length === 0 ? (
        <p className="text-sm text-gray-400">{emptyText}</p>
      ) : (
        <ul className="space-y-1">
          {items.map((item) => (
            <li key={item.id} className="text-sm text-gray-700">
              {item.name || item.id}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export default function OwnershipScopePage() {
  const { scope, loading: scopeLoading, error: scopeError, refetch } = useOwnershipScope()
  const { studios, loading: studiosLoading } = useVisibleStudios()

  const loading = scopeLoading || studiosLoading

  const studioIds = scope?.studio_ids ?? []
  const franchiseIds = scope?.franchise_ids ?? []

  const visibleStudios = studios.filter((s) => studioIds.includes(s.id) || scope?.is_admin)

  return (
    <AppShell>
      <OwnershipPageShell
        title="My Ownership Scope"
        subtitle="Your current access and visibility across studios and franchises"
        actions={<OwnershipVisibilityBadge scope={scope} />}
      >
        <div data-testid="ownership-scope-page">
          {loading && <OwnershipLoading />}
          {!loading && scopeError && <OwnershipError message={scopeError} onRetry={refetch} />}
          {!loading && !scopeError && (
            <div className="space-y-4">
              {scope?.is_admin && (
                <div className="rounded-lg border border-blue-200 bg-blue-50 px-5 py-3">
                  <p className="text-sm text-blue-800 font-medium">Admin — full visibility into all studios and franchises.</p>
                </div>
              )}

              <div className="grid gap-4 md:grid-cols-2">
                <ScopeSection
                  title="Visible Studios"
                  items={visibleStudios}
                  emptyText="No studios in your current scope."
                  testId="scope-studios-section"
                />
                <ScopeSection
                  title="Franchise IDs in Scope"
                  items={franchiseIds.map((id) => ({ id, name: id }))}
                  emptyText="No franchises in your current scope."
                  testId="scope-franchises-section"
                />
              </div>

              {!scope?.is_admin && studioIds.length === 0 && franchiseIds.length === 0 && (
                <p className="text-sm text-gray-500">
                  You do not have any ownership assignments. Contact an admin to be assigned as a studio or franchise owner.
                </p>
              )}
            </div>
          )}
        </div>
      </OwnershipPageShell>
    </AppShell>
  )
}
