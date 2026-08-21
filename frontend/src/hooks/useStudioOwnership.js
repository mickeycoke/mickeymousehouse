import { useState, useEffect, useCallback } from 'react'
import {
  assignStudioOwner,
  getStudioOwners,
  removeStudioOwner,
  updateStudioOwner,
} from '../api/ownership'
import { getApiErrorMessage } from '../utils/apiError'

function getErrorMessage(err, fallback) {
  return getApiErrorMessage(err, fallback)
}

export function useStudioOwnership({ studioId, userId, includeInactive = false } = {}) {
  const [studioOwners, setStudioOwners] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchStudioOwners = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getStudioOwners({ studioId, userId, includeInactive })
      setStudioOwners(data)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load studio owners'))
    } finally {
      setLoading(false)
    }
  }, [studioId, userId, includeInactive])

  useEffect(() => {
    fetchStudioOwners()
  }, [fetchStudioOwners])

  const assign = useCallback(async (payload) => {
    const data = await assignStudioOwner(payload)
    await fetchStudioOwners()
    return data
  }, [fetchStudioOwners])

  const update = useCallback(async (id, payload) => {
    const data = await updateStudioOwner(id, payload)
    await fetchStudioOwners()
    return data
  }, [fetchStudioOwners])

  const remove = useCallback(async (id) => {
    const data = await removeStudioOwner(id)
    await fetchStudioOwners()
    return data
  }, [fetchStudioOwners])

  return {
    studioOwners,
    loading,
    error,
    refetch: fetchStudioOwners,
    assignStudioOwner: assign,
    updateStudioOwner: update,
    removeStudioOwner: remove,
  }
}
