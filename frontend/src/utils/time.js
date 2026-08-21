// Timestamps from the API are stored in UTC but serialized WITHOUT a zone
// marker. Parse them as UTC so they render in the viewer's local time.
export function ts(iso) {
  if (!iso) return null
  const s = String(iso)
  // Already carries a zone (Z or ±hh:mm) — parse verbatim.
  if (/Z$|[+-]\d{2}:?\d{2}$/.test(s)) return new Date(s)
  // DATE-ONLY ("2024-01-15"), e.g. a bucketed weekly/monthly point. Appending a
  // bare "Z" yields "2024-01-15Z" — V8 tolerates it but Safari/WebKit returns
  // Invalid Date, which cascaded into "Invalid Date" axis labels. Parse as
  // LOCAL midnight so the calendar date renders verbatim (no zone shift) in
  // every browser.
  if (!s.includes('T')) return new Date(`${s}T00:00:00`)
  // Zoneless date-time: mark it UTC.
  return new Date(`${s}Z`)
}

// Common IANA choices for the studio settings dropdowns
export const TIMEZONES = [
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Phoenix',
  'America/Los_Angeles',
  'America/Anchorage',
  'Pacific/Honolulu',
  'UTC',
]
