// P2-050: Layout wrapper for setup/admin pages
export default function SetupPageShell({ title, subtitle, actions, children }) {
  return (
    <div className="px-8 py-6" data-testid="setup-page-shell">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
        </div>
        {actions && <div className="flex gap-3">{actions}</div>}
      </div>
      {children}
    </div>
  )
}
