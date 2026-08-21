import { useState, useEffect, useCallback } from 'react'
import {
  assignFranchiseStudio,
  getFranchiseStudios,
  removeFranchiseStudio,
  updateFranchiseStudio,
} from '../api/ownership'
import { getApiErrorMessage } from '../utils/apiError'

function getErrorMessage(err, fallback) {
  return getApiErrorMessage(err, fallback)
}

export function useFranchiseStudios({ franchiseId, studioId, includeInactive = false } = {}) {
  const [franchiseStudios, setFranchiseStudios] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchFranchiseStudios = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getFranchiseStudios({ franchiseId, studioId, includeInactive })
      setFranchiseStudios(data)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load franchise studios'))
    } finally {
      setLoading(false)
    }
  }, [franchiseId, studioId, includeInactive])

  useEffect(() => {
    fetchFranchiseStudios()
  }, [fetchFranchiseStudios])

  const assign = useCallback(async (payload) => {
    const data = await assignFranchiseStudio(payload)
    await fetchFranchiseStudios()
    return data
  }, [fetchFranchiseStudios])

  const update = useCallback(async (id, payload) => {
    const data = await updateFranchiseStudio(id, payload)
    await fetchFranchiseStudios()
    return data
  }, [fetchFranchiseStudios])

  const remove = useCallback(async (id) => {
    const data = await removeFranchiseStudio(id)
    await fetchFranchiseStudios()
    return data
  }, [fetchFranchiseStudios])

  return {
    franchiseStudios,
    loading,
    error,
    refetch: fetchFranchiseStudios,
    assignFranchiseStudio: assign,
    updateFranchiseStudio: update,
    removeFranchiseStudio: remove,
  }
}
