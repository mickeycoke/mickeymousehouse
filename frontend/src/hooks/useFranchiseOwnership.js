import { useState, useEffect, useCallback } from 'react'
import {
  assignFranchiseOwner,
  getFranchiseOwners,
  removeFranchiseOwner,
  updateFranchiseOwner,
} from '../api/ownership'
import { getApiErrorMessage } from '../utils/apiError'

function getErrorMessage(err, fallback) {
  return getApiErrorMessage(err, fallback)
}

export function useFranchiseOwnership({ franchiseId, userId, includeInactive = false } = {}) {
  const [franchiseOwners, setFranchiseOwners] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchFranchiseOwners = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getFranchiseOwners({ franchiseId, userId, includeInactive })
      setFranchiseOwners(data)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load franchise owners'))
    } finally {
      setLoading(false)
    }
  }, [franchiseId, userId, includeInactive])

  useEffect(() => {
    fetchFranchiseOwners()
  }, [fetchFranchiseOwners])

  const assign = useCallback(async (payload) => {
    const data = await assignFranchiseOwner(payload)
    await fetchFranchiseOwners()
    return data
  }, [fetchFranchiseOwners])

  const update = useCallback(async (id, payload) => {
    const data = await updateFranchiseOwner(id, payload)
    await fetchFranchiseOwners()
    return data
  }, [fetchFranchiseOwners])

  const remove = useCallback(async (id) => {
    const data = await removeFranchiseOwner(id)
    await fetchFranchiseOwners()
    return data
  }, [fetchFranchiseOwners])

  return {
    franchiseOwners,
    loading,
    error,
    refetch: fetchFranchiseOwners,
    assignFranchiseOwner: assign,
    updateFranchiseOwner: update,
    removeFranchiseOwner: remove,
  }
}
