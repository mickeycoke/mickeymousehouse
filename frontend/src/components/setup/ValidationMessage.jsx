// P2-053: Consistent inline form error display
// Props: message (string|null), fieldErrors? ({[field]: string})

// API error payloads are not always strings — FastAPI 422s send an array of
// {loc, msg, ...} objects. Rendering an object as a React child crashes the
// whole app, so normalize everything to a string here.
function toDisplayString(message) {
  if (message == null) return null
  if (typeof message === 'string') return message
  if (Array.isArray(message)) {
    return message
      .map((item) => (typeof item === 'string' ? item : item?.msg || JSON.stringify(item)))
      .join('; ')
  }
  if (typeof message === 'object') {
    return message.msg || message.message || JSON.stringify(message)
  }
  return String(message)
}

export default function ValidationMessage({ message, fieldErrors }) {
  const displayMessage = toDisplayString(message)
  const hasFieldErrors = fieldErrors && Object.keys(fieldErrors).length > 0

  if (!displayMessage && !hasFieldErrors) return null

  return (
    <div
      className="rounded-md bg-red-50 border border-red-200 p-3"
      data-testid="validation-message"
    >
      {displayMessage && (
        <p className="text-sm text-red-700 font-medium">{displayMessage}</p>
      )}
      {hasFieldErrors && (
        <ul className="mt-1 space-y-1">
          {Object.entries(fieldErrors).map(([field, error]) => (
            <li
              key={field}
              className="text-sm text-red-600"
              data-testid="validation-field-error"
            >
              <span className="font-medium capitalize">{field}:</span> {error}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
