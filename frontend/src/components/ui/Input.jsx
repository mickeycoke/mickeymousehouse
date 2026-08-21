export default function Input({
  id,
  label,
  error,
  testId,
  type = 'text',
  required = false,
  ...props
}) {
  return (
    <div>
      {label && (
        <label htmlFor={id} className="block text-sm font-medium text-gray-700 mb-1">
          {label}
          {required && <span className="text-red-500 ml-0.5">*</span>}
        </label>
      )}
      <input
        id={id}
        type={type}
        data-testid={testId}
        data-error={error ? 'true' : undefined}
        required={required}
        className={`
          w-full border rounded-lg px-3 py-2 text-sm
          focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
          ${error ? 'border-red-300 bg-red-50' : 'border-gray-300 bg-white'}
        `}
        {...props}
      />
      {error && (
        <p data-testid={`${testId}-error`} className="mt-1 text-xs text-red-600">
          {error}
        </p>
      )}
    </div>
  )
}
