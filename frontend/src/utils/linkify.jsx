// Render plain text with bare http(s) URLs turned into clickable links.
// Text stays text — no markdown, no HTML injection; only the URL substrings
// become anchors.
const URL_RE = /(https?:\/\/[^\s<>"')\]]+)/g

export function renderWithLinks(text) {
  if (!text) return text
  const parts = String(text).split(URL_RE)
  if (parts.length === 1) return text
  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <a key={i} href={part} target="_blank" rel="noopener noreferrer"
        className="text-blue-600 underline break-all">
        {part}
      </a>
    ) : part
  )
}
