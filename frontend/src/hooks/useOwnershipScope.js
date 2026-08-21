import { useState, useEffect, useCallback } from 'react'
import { getOwnershipScope, getStudios } from '../api/ownership'
import { getApiErrorMessage } from '../utils/apiError'

function getErrorMessage(err, fallback) {
  return getApiErrorMessage(err, fallback)
}

export function useOwnershipScope() {
  const [scope, setScope] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchScope = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getOwnershipScope()
      setScope(data)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load ownership scope'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchScope()
  }, [fetchScope])

  return { scope, loading, error, refetch: fetchScope }
}

export function useVisibleStudios({ includeInactive = false } = {}) {
  const [studios, setStudios] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchStudios = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getStudios({ includeInactive })
      setStudios(data)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load visible studios'))
    } finally {
      setLoading(false)
    }
  }, [includeInactive])

  useEffect(() => {
    fetchStudios()
  }, [fetchStudios])

  return { studios, loading, error, refetch: fetchStudios }
}
