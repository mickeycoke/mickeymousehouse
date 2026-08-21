import { createContext, useContext, useEffect, useState } from 'react'

// Admin-only "operating studio": when set, the whole app is scoped to that
// studio (its clients, instructors, dashboard, history…). Persisted so it
// survives reloads, and mirrored to localStorage where the api client reads it
// to send the X-Studio-Id header on every request.
const StudioContext = createContext(null)

export function StudioProvider({ children }) {
  const [studio, setStudioState] = useState(() => {
    try {
      const raw = localStorage.getItem('pt-operating-studio')
      return raw ? JSON.parse(raw) : null
    } catch { return null }
  })

  useEffect(() => {
    try {
      if (studio) localStorage.setItem('pt-operating-studio', JSON.stringify(studio))
      else localStorage.removeItem('pt-operating-studio')
    } catch { /* storage unavailable */ }
  }, [studio])

  const setStudio = (s) => setStudioState(s ? { id: s.id, name: s.name } : null)
  const clearStudio = () => setStudioState(null)

  return (
    <StudioContext.Provider value={{ studio, setStudio, clearStudio }}>
      {children}
    </StudioContext.Provider>
  )
}

export function useOperatingStudio() {
  return useContext(StudioContext) ?? { studio: null, setStudio: () => {}, clearStudio: () => {} }
}
