// Normalize any API error into a display-safe string.
//
// Rendering a non-string as a React child crashes the whole app, and this
// backend returns several detail shapes:
//   - plain string                              (most 400/403/404s)
//   - array of {loc, msg, type, input, ctx}     (FastAPI 422 validation)
//   - {error: {code, message, field}}           (reporting errors)
//   - {code, message} / {message, ...}          (session conflicts/warnings)
//
// Every component and hook must go through this helper before putting an
// API error into rendered state. Never render err.response.data.detail raw.
export function getApiErrorMessage(err, fallback = 'Something went wrong') {
  const detail = err?.response?.data?.detail

  if (detail == null) return err?.message || fallback
  if (typeof detail === 'string') return detail

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (typeof item === 'string' ? item : item?.msg))
      .filter(Boolean)
    return messages.length ? messages.join('; ') : fallback
  }

  if (typeof detail === 'object') {
    return detail.error?.message || detail.message || detail.msg || fallback
  }

  return String(detail)
}
