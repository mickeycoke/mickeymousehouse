import { useRef } from 'react'

// Composer chrome for pictures: an "Add image" button (file picker) plus the
// row of pending thumbnails with a remove ✕. Pasting into the composer's
// textarea is wired separately via useAttachmentDrafts().onPaste.
export function AddImageButton({ onFiles, testId = 'attach-image' }) {
  const inputRef = useRef(null)
  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept="image/*,.md,.markdown"
        multiple
        className="hidden"
        data-testid={`${testId}-input`}
        onChange={(e) => { onFiles(e.target.files); e.target.value = '' }}
      />
      <button
        type="button"
        data-testid={testId}
        onClick={() => inputRef.current?.click()}
        className="text-xs font-medium text-blue-600 hover:underline"
      >
        Add image
      </button>
    </>
  )
}

export function DraftStrip({ drafts, onRemove }) {
  if (!drafts.length) return null
  return (
    <div className="mt-2 flex flex-wrap gap-2" data-testid="draft-strip">
      {drafts.map((d) => (
        <div key={d.key} className="relative">
          <img
            src={d.previewUrl}
            alt={d.filename}
            className={`h-16 w-16 rounded-lg border object-cover ${
              d.error ? 'border-red-300 opacity-40' : d.id ? 'border-gray-200' : 'border-gray-200 opacity-50'
            }`}
          />
          {d.error && (
            <span className="absolute inset-x-0 bottom-0 rounded-b-lg bg-red-600/80 text-center text-[9px] text-white">
              failed
            </span>
          )}
          <button
            type="button"
            aria-label="Remove image"
            onClick={() => onRemove(d.key)}
            className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-gray-700 text-[10px] leading-none text-white hover:bg-gray-900"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  )
}
