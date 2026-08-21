export default function OwnershipPageShell({ title, subtitle, actions, children }) {
  return (
    <div className="px-8 py-6" data-testid="ownership-page-shell">
      <div className="flex items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
        </div>
        {actions && <div className="flex flex-wrap gap-3 justify-end">{actions}</div>}
      </div>
      {children}
    </div>
  )
}
