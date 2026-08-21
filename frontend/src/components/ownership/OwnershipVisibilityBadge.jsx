import Badge from '../ui/Badge'

export default function OwnershipVisibilityBadge({ scope }) {
  if (!scope) return <Badge color="gray">Unknown scope</Badge>
  if (scope.is_admin) return <Badge color="blue">Admin visibility</Badge>

  const studioCount = scope.studio_ids?.length ?? 0
  const franchiseCount = scope.franchise_ids?.length ?? 0

  if (franchiseCount > 0) {
    return <Badge color="green">{franchiseCount} franchise scope</Badge>
  }
  if (studioCount > 0) {
    return <Badge color="amber">{studioCount} studio scope</Badge>
  }
  return <Badge color="gray">No ownership scope</Badge>
}
