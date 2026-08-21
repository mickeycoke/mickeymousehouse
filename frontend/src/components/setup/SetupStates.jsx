import Button from '../ui/Button'

// P2-054: Reusable loading, empty, and error state components for setup pages

export function SetupLoading({ message = 'Loading...' }) {
  return (
    <div
      className="flex items-center justify-center py-16 text-gray-500"
      data-testid="setup-loading"
    >
      <svg
        className="animate-spin h-5 w-5 mr-3 text-blue-500"
        viewBox="0 0 24 24"
        fill="none"
      >
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8v8H4z"
        />
      </svg>
      <span className="text-sm">{message}</span>
    </div>
  )
}

export function SetupEmpty({ message = 'No records found.' }) {
  return (
    <div
      className="flex items-center justify-center py-16 text-gray-400"
      data-testid="setup-empty"
    >
      <p className="text-sm">{message}</p>
    </div>
  )
}

export function SetupError({ message, onRetry }) {
  return (
    <div
      className="flex flex-col items-center justify-center py-16 gap-3"
      data-testid="setup-error"
    >
      <p className="text-sm text-red-600">{message}</p>
      {onRetry && (
        <Button
          variant="secondary"
          size="sm"
          onClick={onRetry}
          testId="setup-error-retry"
        >
          Retry
        </Button>
      )}
    </div>
  )
}
