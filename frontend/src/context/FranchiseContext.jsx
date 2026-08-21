import { createContext, useContext, useEffect, useState } from 'react'

// Admin's "operating franchise": the sidebar reads
// Franchise → Studios → Instructors → Clients, and selecting a franchise on
// the Franchise tab filters the Studios tab to that franchise. Persisted so
// the drill-down survives reloads.
const FranchiseContext = createContext(null)

export function FranchiseProvider({ children }) {
  const [franchise, setFranchiseState] = useState(() => {
    try {
      const raw = localStorage.getItem('pt-operating-franchise')
      return raw ? JSON.parse(raw) : null
    } catch { return null }
  })

  useEffect(() => {
    try {
      if (franchise) localStorage.setItem('pt-operating-franchise', JSON.stringify(franchise))
      else localStorage.removeItem('pt-operating-franchise')
    } catch { /* storage unavailable */ }
  }, [franchise])

  const setFranchise = (f) => setFranchiseState(f ? { id: f.id, name: f.name } : null)
  const clearFranchise = () => setFranchiseState(null)

  return (
    <FranchiseContext.Provider value={{ franchise, setFranchise, clearFranchise }}>
      {children}
    </FranchiseContext.Provider>
  )
}

export function useOperatingFranchise() {
  return useContext(FranchiseContext) ?? { franchise: null, setFranchise: () => {}, clearFranchise: () => {} }
}
