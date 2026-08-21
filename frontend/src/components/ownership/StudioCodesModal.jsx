import { useEffect, useState } from 'react'
import Modal from '../ui/Modal'
import { getStudioAccessCodes } from '../../api/ownership'

// Shows a studio's onboarding + shared-device links & QR codes so the owner /
// manager can hand them to instructors and set up the front-desk tablet.
function CodeBlock({ title, subtitle, data, testId }) {
  const [copied, setCopied] = useState(false)
  if (!data) return null
  return (
    <div className="rounded-lg border border-gray-200 p-4" data-testid={testId}>
      <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
      <p className="mb-3 text-xs text-gray-500">{subtitle}</p>
      <div className="flex items-center gap-4">
        <img
          src={`data:image/png;base64,${data.qr}`}
          alt={`${title} QR code`}
          className="h-32 w-32 shrink-0 rounded border border-gray-200"
        />
        <div className="min-w-0 flex-1">
          <p className="break-all rounded bg-gray-50 px-2 py-1 text-xs text-gray-700">{data.url}</p>
          <button
            type="button"
            onClick={() => { navigator.clipboard?.writeText(data.url); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
            className="mt-2 rounded-lg border border-gray-300 px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
          >
            {copied ? 'Copied!' : 'Copy link'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function StudioCodesModal({ studio, onClose }) {
  const [codes, setCodes] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    setCodes(null)
    setError(null)
    if (!studio?.id) return
    getStudioAccessCodes(studio.id)
      .then(setCodes)
      .catch(() => setError('Can’t connect to studio when impersonating another.'))
  }, [studio?.id])

  const name = studio?.display_name || studio?.name || codes?.studio_name || ''

  return (
    <Modal isOpen={!!studio} onClose={onClose} title={`Onboarding & shared device${name ? ` — ${name}` : ''}`}>
      <div className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto" data-testid="studio-codes-modal">
        {error && <p className="text-sm text-red-600">{error}</p>}
        {!codes && !error && <p className="text-sm text-gray-400">Loading…</p>}
        {codes && (
          <>
            <p className="text-xs text-gray-500">
              Studio code: <span className="font-mono font-medium text-gray-700">{codes.studio_code}</span>
            </p>
            <CodeBlock
              title="Instructor onboarding"
              subtitle="Give this to a new instructor. They scan it, pick their name, and set their own password."
              data={codes.onboard}
              testId="studio-codes-onboard"
            />
            <CodeBlock
              title="Shared front-desk device"
              subtitle="Open this on the studio tablet. Instructors then tap their name and enter their PIN to sign in."
              data={codes.shared}
              testId="studio-codes-shared"
            />
          </>
        )}
      </div>
    </Modal>
  )
}
