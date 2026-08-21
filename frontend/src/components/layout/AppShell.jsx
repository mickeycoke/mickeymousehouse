import { useState } from 'react'
import Sidebar from './Sidebar'
import ContextBar from './ContextBar'
import LoginNotesModal from '../notes/LoginNotesModal'

// Layout shell. On desktop/tablet (md and up) the sidebar is always visible.
// On phones it auto-hides behind the ☰ in the ContextBar and slides in as a
// drawer. The ContextBar (studio · instructor · client pills) sits above the
// page content on every screen — impersonation now shows there as a pill.
export default function AppShell({ children }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  return (
    <div className="flex h-screen flex-col bg-gray-50">
      {/* Admin announcements — shows once per session, anywhere in the app */}
      <LoginNotesModal />
      <div className="flex min-h-0 flex-1">
        {/* Persistent sidebar — tablet/desktop */}
        <div className="hidden h-full md:block">
          <Sidebar />
        </div>

        {/* Slide-in drawer — phones */}
        {mobileNavOpen && (
          <div className="fixed inset-0 z-40 md:hidden">
            <div
              data-testid="mobile-nav-backdrop"
              aria-hidden="true"
              onClick={() => setMobileNavOpen(false)}
              className="absolute inset-0 bg-black/40"
            />
            <div className="absolute inset-y-0 left-0 shadow-xl">
              <Sidebar onNavigate={() => setMobileNavOpen(false)} />
            </div>
          </div>
        )}

        {/* Main column: context header + scrolling page */}
        <div className="flex min-w-0 flex-1 flex-col">
          <ContextBar onMenu={() => setMobileNavOpen(true)} />
          {/* pb-safe-inset: on an iPhone the home indicator overlays the
              bottom of the viewport, so the last rows of any scrolling page
              were cropped behind it. Only five session screens padded for this
              individually; putting it on the shell's scroll region covers every
              page — Setup, Reports, Clients, Dashboard — instead of waiting for
              each one to be reported. On anything without a safe area the inset
              is 0, so nothing changes. */}
          <main className="flex-1 overflow-y-auto pb-safe-inset">
            {children}
          </main>
        </div>
      </div>
    </div>
  )
}
