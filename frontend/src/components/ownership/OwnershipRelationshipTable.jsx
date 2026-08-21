import { SetupEmpty, SetupError, SetupLoading } from '../setup/SetupStates'

export default function OwnershipRelationshipTable({
  columns = [],
  rows = [],
  loading = false,
  error = null,
  emptyMessage = 'No ownership relationships found.',
  onRowClick,
}) {
  if (loading) return <SetupLoading message="Loading ownership relationships..." />
  if (error) return <SetupError message={error} />
  if (rows.length === 0) return <SetupEmpty message={emptyMessage} />

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200" data-testid="ownership-relationship-table">
      <table className="w-full text-sm text-left">
        <thead className="bg-gray-50 text-gray-600 uppercase text-xs">
          <tr>
            {columns.map((column) => (
              <th key={column.key} className="px-4 py-3 font-medium tracking-wide">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {rows.map((row, index) => (
            <tr
              key={row.id ?? index}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={onRowClick ? 'cursor-pointer hover:bg-gray-50 transition-colors' : ''}
              data-testid="ownership-relationship-row"
            >
              {columns.map((column) => (
                <td key={column.key} className="px-4 py-3 text-gray-700">
                  {column.render ? column.render(row) : row[column.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
