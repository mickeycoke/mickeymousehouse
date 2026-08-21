import { renderWithLinks } from './linkify'

// Markdown for broadcast notes — headings, emphasis, lists, links, code, rules,
// quotes and tables.
//
// WHY NOT A LIBRARY. Notes were plain text with `whitespace-pre-wrap`, so a
// pasted release note rendered as a wall of `##` and `**`. `marked` or
// `react-markdown` would do more than this, but they arrive with a dependency
// tree that then renders admin-authored text, and this app has exactly one
// markdown surface. This covers what a note actually uses and is small enough to
// read in one sitting.
//
// SAFETY: this NEVER emits raw HTML. Everything becomes React elements, so a
// note containing `<script>` or `<img onerror=…>` is displayed as literal text
// rather than parsed. That is deliberate — notes are admin-authored, but "the
// author is trusted" is not a security model, and the admin could be pasting
// something they were sent.
//
// Inline text still runs through renderWithLinks, so bare URLs stay clickable
// exactly as before markdown existed.

// `**bold**` `*italic*` `_italic_` `` `code` `` `[text](url)`
const INLINE_RE = /(\*\*[^*]+\*\*|\*[^*\n]+\*|_[^_\n]+_|`[^`\n]+`|\[[^\]]+\]\([^)\s]+\))/g

function renderInline(text, keyPrefix = '') {
  const parts = String(text).split(INLINE_RE)
  return parts.map((part, i) => {
    const key = `${keyPrefix}i${i}`
    if (!part) return null
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={key} className="font-semibold">{part.slice(2, -2)}</strong>
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code key={key} className="rounded bg-gray-100 px-1 py-0.5 font-mono text-[0.92em]">
          {part.slice(1, -1)}
        </code>
      )
    }
    if (part.startsWith('[')) {
      const m = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(part)
      if (m) {
        return (
          <a key={key} href={m[2]} target="_blank" rel="noopener noreferrer"
            className="text-blue-600 underline">
            {m[1]}
          </a>
        )
      }
    }
    if ((part.startsWith('*') && part.endsWith('*')) || (part.startsWith('_') && part.endsWith('_'))) {
      return <em key={key} className="italic">{part.slice(1, -1)}</em>
    }
    // Plain run — keep bare-URL autolinking.
    return <span key={key}>{renderWithLinks(part)}</span>
  })
}

const HEADING_CLASS = {
  1: 'mt-4 mb-2 text-lg font-bold text-gray-900',
  2: 'mt-4 mb-1.5 text-base font-bold text-gray-900',
  3: 'mt-3 mb-1 text-sm font-semibold text-gray-900',
}

function splitRow(line) {
  return line.replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
}

export function renderMarkdown(source) {
  if (!source) return null
  const lines = String(source).replace(/\r\n/g, '\n').split('\n')
  const out = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // Fenced code — taken verbatim, no inline parsing inside.
    if (/^```/.test(line)) {
      const body = []
      i += 1
      while (i < lines.length && !/^```/.test(lines[i])) { body.push(lines[i]); i += 1 }
      i += 1
      out.push(
        <pre key={`c${i}`} className="my-2 overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs leading-relaxed text-gray-100">
          <code>{body.join('\n')}</code>
        </pre>,
      )
      continue
    }

    // Table: a header row followed by a |---|---| separator.
    if (line.includes('|') && /^\s*\|?[\s:-]*-[\s:|-]*$/.test(lines[i + 1] ?? '')) {
      const header = splitRow(line)
      i += 2
      const rows = []
      while (i < lines.length && lines[i].includes('|')) { rows.push(splitRow(lines[i])); i += 1 }
      out.push(
        <div key={`t${i}`} className="my-2 overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr>
                {header.map((h, hi) => (
                  <th key={hi} className="border-b border-gray-300 px-2 py-1 text-left font-semibold text-gray-700">
                    {renderInline(h, `th${hi}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>
                  {r.map((c, ci) => (
                    <td key={ci} className="border-b border-gray-100 px-2 py-1 align-top text-gray-600">
                      {renderInline(c, `td${ri}-${ci}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }

    const heading = /^(#{1,3})\s+(.*)$/.exec(line)
    if (heading) {
      const level = heading[1].length
      const Tag = `h${level + 1}`   // note bodies sit under a page h1/h2
      out.push(
        <Tag key={`h${i}`} className={HEADING_CLASS[level]}>
          {renderInline(heading[2], `h${i}`)}
        </Tag>,
      )
      i += 1
      continue
    }

    if (/^\s*(---+|\*\*\*+)\s*$/.test(line)) {
      out.push(<hr key={`r${i}`} className="my-3 border-gray-200" />)
      i += 1
      continue
    }

    // Bullet or numbered list — consecutive markers of the same kind.
    const bullet = /^\s*[-*+]\s+(.*)$/.exec(line)
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line)
    if (bullet || numbered) {
      const ordered = Boolean(numbered)
      const items = []
      while (i < lines.length) {
        const m = ordered
          ? /^\s*\d+[.)]\s+(.*)$/.exec(lines[i])
          : /^\s*[-*+]\s+(.*)$/.exec(lines[i])
        if (!m) break
        items.push(m[1])
        i += 1
      }
      const List = ordered ? 'ol' : 'ul'
      out.push(
        <List key={`l${i}`} className={`my-2 space-y-1 pl-5 ${ordered ? 'list-decimal' : 'list-disc'}`}>
          {items.map((it, ii) => <li key={ii}>{renderInline(it, `l${i}-${ii}`)}</li>)}
        </List>,
      )
      continue
    }

    if (/^\s*>\s?/.test(line)) {
      const quote = []
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        quote.push(lines[i].replace(/^\s*>\s?/, '')); i += 1
      }
      out.push(
        <blockquote key={`q${i}`} className="my-2 border-l-2 border-blue-300 pl-3 text-gray-600">
          {renderInline(quote.join(' '), `q${i}`)}
        </blockquote>,
      )
      continue
    }

    if (line.trim() === '') { i += 1; continue }

    // Paragraph: consecutive non-blank lines that start no other block.
    const para = []
    while (
      i < lines.length && lines[i].trim() !== ''
      && !/^(#{1,3}\s|```|\s*[-*+]\s|\s*\d+[.)]\s|\s*>|\s*(---+|\*\*\*+)\s*$)/.test(lines[i])
    ) {
      para.push(lines[i]); i += 1
    }
    out.push(
      <p key={`p${i}`} className="my-2 leading-relaxed">
        {renderInline(para.join(' '), `p${i}`)}
      </p>,
    )
  }

  return out
}
