import { useState, useEffect, useCallback } from 'react'
import {
  createFranchise,
  deactivateFranchise,
  getFranchise,
  getFranchises,
  updateFranchise,
} from '../api/ownership'
import { getApiErrorMessage } from '../utils/apiError'

function getErrorMessage(err, fallback) {
  return getApiErrorMessage(err, fallback)
}

export function useFranchises({ includeInactive = false } = {}) {
  const [franchises, setFranchises] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchFranchises = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getFranchises({ includeInactive })
      setFranchises(data)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load franchises'))
    } finally {
      setLoading(false)
    }
  }, [includeInactive])

  useEffect(() => {
    fetchFranchises()
  }, [fetchFranchises])

  const create = useCallback(async (payload) => {
    const data = await createFranchise(payload)
    await fetchFranchises()
    return data
  }, [fetchFranchises])

  const update = useCallback(async (id, payload) => {
    const data = await updateFranchise(id, payload)
    await fetchFranchises()
    return data
  }, [fetchFranchises])

  const deactivate = useCallback(async (id) => {
    const data = await deactivateFranchise(id)
    await fetchFranchises()
    return data
  }, [fetchFranchises])

  return {
    franchises,
    loading,
    error,
    refetch: fetchFranchises,
    createFranchise: create,
    updateFranchise: update,
    deactivateFranchise: deactivate,
  }
}

export function useFranchise(id) {
  const [franchise, setFranchise] = useState(null)
  const [loading, setLoading] = useState(Boolean(id))
  const [error, setError] = useState(null)

  const fetchFranchise = useCallback(async () => {
    if (!id) {
      setFranchise(null)
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)
    try {
      const data = await getFranchise(id)
      setFranchise(data)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load franchise'))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    fetchFranchise()
  }, [fetchFranchise])

  return { franchise, loading, error, refetch: fetchFranchise }
}
