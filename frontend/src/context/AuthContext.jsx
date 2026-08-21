import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import client from '../api/client'
import { getMyRoles } from '../api/roles'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [impersonator, setImpersonator] = useState(null)
  const [myRoles, setMyRoles] = useState(null)
  const [loading, setLoading] = useState(true)

  // Load the user's hats whenever the acting user changes
  useEffect(() => {
    if (!user) { setMyRoles(null); return }
    getMyRoles().then(setMyRoles).catch(() => setMyRoles(null))
  }, [user])

  useEffect(() => {
    const stored = localStorage.getItem('auth_user')
    const token = localStorage.getItem('access_token')
    if (stored && token) {
      try {
        setUser(JSON.parse(stored))
      } catch {
        localStorage.removeItem('auth_user')
      }
    }
    // Restore an in-flight impersonation across reloads
    const adminStored = localStorage.getItem('admin_user')
    if (adminStored && localStorage.getItem('admin_token')) {
      try {
        setImpersonator(JSON.parse(adminStored))
      } catch {
        localStorage.removeItem('admin_user')
        localStorage.removeItem('admin_token')
      }
    }
    setLoading(false)
  }, [])

  const login = useCallback((userData, accessToken) => {
    localStorage.setItem('access_token', accessToken)
    localStorage.setItem('auth_user', JSON.stringify(userData))
    setUser(userData)
  }, [])

  // `to` lets a caller land somewhere other than the default login screen
  // after signing out, without every existing caller needing to change.
  const logout = useCallback(async (to = '/login') => {
    try {
      await client.post('/auth/logout')
    } catch {
      // ignore — clearing state regardless
    }
    ;['access_token', 'auth_user', 'admin_token', 'admin_user',
      'pt-operating-studio'].forEach((k) => localStorage.removeItem(k))
    // Full reload so the Studio context provider (mounted above the router)
    // resets too — otherwise the previous user's studio survives into the
    // next login on a shared device.
    window.location.href = to
  }, [])

  // Admin testing aid: act as another user while keeping the admin token
  // stored locally, so "return to admin" is instant and offline-safe.
  const impersonate = useCallback((targetUser, targetToken) => {
    const adminToken = localStorage.getItem('access_token')
    const adminUser = localStorage.getItem('auth_user')
    localStorage.setItem('admin_token', adminToken)
    localStorage.setItem('admin_user', adminUser)
    localStorage.setItem('access_token', targetToken)
    localStorage.setItem('auth_user', JSON.stringify(targetUser))
    setImpersonator(JSON.parse(adminUser))
    setUser(targetUser)
  }, [])

  const exitImpersonation = useCallback(() => {
    const adminToken = localStorage.getItem('admin_token')
    const adminUser = localStorage.getItem('admin_user')
    if (!adminToken || !adminUser) return
    localStorage.setItem('access_token', adminToken)
    localStorage.setItem('auth_user', adminUser)
    localStorage.removeItem('admin_token')
    localStorage.removeItem('admin_user')
    setUser(JSON.parse(adminUser))
    setImpersonator(null)
  }, [])

  const isAdmin = user?.role === 'admin'
  const isAuthenticated = !!user
  const isImpersonating = !!impersonator

  return (
    <AuthContext.Provider
      value={{ user, impersonator, isImpersonating, myRoles, loading, isAuthenticated, isAdmin, login, logout, impersonate, exitImpersonation }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
