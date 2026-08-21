import Button from '../ui/Button'

export function OwnershipLoading({ message = 'Loading ownership data...' }) {
  return (
    <div className="flex items-center justify-center py-16 text-gray-500" data-testid="ownership-loading">
      <svg className="animate-spin h-5 w-5 mr-3 text-blue-500" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
      </svg>
      <span className="text-sm">{message}</span>
    </div>
  )
}

export function OwnershipEmpty({ message = 'No ownership records found.' }) {
  return (
    <div className="flex items-center justify-center py-16 text-gray-400" data-testid="ownership-empty">
      <p className="text-sm">{message}</p>
    </div>
  )
}

export function OwnershipError({ message, onRetry }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3" data-testid="ownership-error">
      <p className="text-sm text-red-600">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} testId="ownership-error-retry">
          Retry
        </Button>
      )}
    </div>
  )
}

export function OwnershipUnauthorized({
  title = 'Ownership access required',
  message = 'You do not have permission to view or manage this ownership area.',
}) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-5 py-4" data-testid="ownership-unauthorized">
      <h2 className="text-sm font-semibold text-amber-900">{title}</h2>
      <p className="mt-1 text-sm text-amber-800">{message}</p>
    </div>
  )
}
