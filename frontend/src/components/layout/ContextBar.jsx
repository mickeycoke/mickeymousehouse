import { IconMenu2, IconBuildingCommunity, IconX, IconUserShare } from '@tabler/icons-react'
import { useAuth } from '../../context/AuthContext'
import { useOperatingStudio } from '../../context/StudioContext'
import { APP_NAME } from '../../config/brand'

// The persistent context header. It carries up to two dismissable pills:
//   Studio (admin)  — which tenant the admin is operating within
//   Instructor      — who the admin is impersonating (requires a studio)
// Selecting/clearing a studio reloads so every screen refetches at the new
// scope (the api client sends X-Studio-Id from the persisted selection).
export default function ContextBar({ onMenu }) {
  const { user, myRoles, isAdmin, isImpersonating, exitImpersonation } = useAuth()
  const { studio, setStudio, clearStudio } = useOperatingStudio()
  const myStudios = myRoles?.studios ?? []

  function clearStudioContext() {
    // Leaving a studio drops everything scoped to it.
    if (isImpersonating) exitImpersonation()
    clearStudio()
    window.location.href = '/admin/overview'
  }
  function stopImpersonating() {
    exitImpersonation()
    window.location.href = '/admin/overview'
  }

  return (
    <header
      data-testid="context-bar"
      className="flex shrink-0 items-center gap-2 border-b border-gray-200 bg-white px-3 py-2.5 sm:px-6"
    >
      <button
        type="button"
        data-testid="mobile-nav-toggle"
        aria-label="Open menu"
        onClick={onMenu}
        className="-ml-1 shrink-0 rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 md:hidden"
      >
        <IconMenu2 size={22} />
      </button>

      {/* Studio context. The pill shows whenever an operating studio is set —
          including while impersonating — so both pills stay visible. */}
      {isAdmin ? (
        studio ? (
          <span className="flex min-w-0 items-center" data-testid="context-studio">
            <span className="inline-flex min-w-0 items-center gap-1.5 rounded-l-full bg-blue-600 py-1 pl-2.5 pr-2 text-xs font-semibold text-white">
              <IconBuildingCommunity size={13} className="shrink-0" />
              <span className="max-w-[10rem] truncate">{studio.name}</span>
            </span>
            <button
              type="button"
              data-testid="context-studio-clear"
              onClick={clearStudioContext}
              aria-label="Leave studio"
              className="rounded-r-full bg-blue-600 py-1 pl-0.5 pr-2 text-blue-100 hover:bg-blue-700 hover:text-white"
            >
              <IconX size={13} />
            </button>
          </span>
        ) : (
          <span className="flex min-w-0 items-center gap-2" data-testid="context-studio-all">
            <IconBuildingCommunity size={18} className="shrink-0 text-gray-400" />
            <span className="truncate text-sm font-medium text-gray-500">All studios</span>
          </span>
        )
      ) : myStudios.length > 1 ? (
        <span className="flex min-w-0 items-center gap-1.5" data-testid="context-studio-switcher">
          <IconBuildingCommunity size={16} className="shrink-0 text-blue-600" />
          <select
            value={studio?.id || ''}
            data-testid="context-studio-select"
            onChange={(e) => {
              const s = myStudios.find((x) => x.id === e.target.value)
              if (s) setStudio({ id: s.id, name: s.name }); else clearStudio()
              // Reload so every screen refetches scoped to the newly selected studio.
              window.location.href = '/admin/overview'
            }}
            className="max-w-[12rem] truncate rounded-lg border border-gray-300 bg-white py-1 pl-2 pr-7 text-sm font-medium text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All my studios</option>
            {myStudios.map((s) => (
              <option key={s.id} value={s.id}>{s.name}{s.is_primary ? ' ★' : ''}</option>
            ))}
          </select>
        </span>
      ) : (
        <span className="flex min-w-0 items-center gap-2">
          <IconBuildingCommunity size={18} className="shrink-0 text-gray-400" />
          <span data-testid="context-studio" className="truncate text-sm font-semibold text-gray-900">
            {myRoles?.studio_name || APP_NAME}
          </span>
        </span>
      )}

      <div className="ml-auto flex min-w-0 items-center gap-2">
        {/* Impersonation pill */}
        {isImpersonating && (
          <span className="flex min-w-0 items-center">
            <span className="inline-flex min-w-0 items-center gap-1.5 rounded-l-full bg-amber-400 py-1 pl-2.5 pr-2 text-xs font-semibold text-amber-950">
              <IconUserShare size={13} className="shrink-0" />
              <span className="max-w-[8rem] truncate" data-testid="context-instructor">acting as {user?.name}</span>
            </span>
            <button
              type="button"
              data-testid="context-instructor-clear"
              onClick={stopImpersonating}
              aria-label="Stop acting as instructor"
              className="rounded-r-full bg-amber-400 py-1 pl-0.5 pr-2 text-amber-800 hover:bg-amber-500 hover:text-amber-950"
            >
              <IconX size={13} />
            </button>
          </span>
        )}
      </div>
    </header>
  )
}
