import { useState } from 'react'

// WHICH BRANCH AM I LOOKING AT?
//
// A port number cannot tell you what it serves when more than one dev server
// or worktree is running, so the page says so out loud. The value comes from
// the `pt-dev-build` meta tag that vite.config.js stamps at build time, so
// the badge and any E2E guard read the SAME string — there is no second
// place for it to drift.
//
// Shown in `vite dev` AND in a BUILT app served from localhost — because a
// stale `dist` served on a familiar-looking port is exactly the case a
// dev-only badge would miss. Allowlist, not denylist: only localhost/loopback
// show it, so a real deployment never matches and studios never see it.
function readStamp(name) {
  if (typeof document === 'undefined') return ''
  return document.querySelector(`meta[name="${name}"]`)?.getAttribute('content') || ''
}

function isLocalSurface() {
  if (typeof window === 'undefined') return false
  const h = window.location.hostname
  return h === 'localhost' || h === '127.0.0.1' || h === '::1' || h === '[::1]'
}

export default function DevBadge() {
  const [open, setOpen] = useState(false)
  if (!import.meta.env.DEV && !isLocalSurface()) return null

  const stamp = readStamp('pt-dev-build')
  if (!stamp) return null
  const checkout = readStamp('pt-dev-checkout')
  const dirty = stamp.endsWith('+dirty')

  return (
    <button
      type="button"
      data-testid="dev-build-badge"
      data-build={stamp}
      title={`${stamp}\n${checkout}\nClick to expand`}
      onClick={() => setOpen((v) => !v)}
      className={`fixed bottom-1 left-1 z-[9999] max-w-[92vw] truncate rounded px-1.5 py-0.5 font-mono text-[10px] leading-tight shadow-sm ring-1 ${
        dirty
          ? 'bg-amber-100/90 text-amber-900 ring-amber-300'
          : 'bg-slate-900/80 text-slate-100 ring-slate-700'
      }`}
    >
      {open ? `${stamp} · ${checkout}` : stamp}
    </button>
  )
}
