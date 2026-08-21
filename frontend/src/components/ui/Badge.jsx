const COLOR_MAP = {
  blue:   'bg-blue-100 text-blue-700',
  green:  'bg-green-100 text-green-700',
  amber:  'bg-amber-100 text-amber-700',
  red:    'bg-red-100 text-red-700',
  purple: 'bg-purple-100 text-purple-700',
  gray:   'bg-gray-100 text-gray-600',
}

export default function Badge({ children, color = 'gray', testId }) {
  return (
    <span
      data-testid={testId}
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${COLOR_MAP[color] || COLOR_MAP.gray}`}
    >
      {children}
    </span>
  )
}
