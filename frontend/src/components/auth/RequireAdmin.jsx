import { Navigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { OwnershipUnauthorized } from '../ownership/OwnershipStates'
import AppShell from '../layout/AppShell'
import PageHeader from '../layout/PageHeader'

export default function RequireAdmin({ children }) {
  const { isAdmin, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (isAdmin) return children

  return (
    <AppShell>
      <PageHeader title="Ownership" subtitle="Admin access required" />
      <div className="px-8 py-6">
        <OwnershipUnauthorized />
        <Navigate to="/admin/overview" replace />
      </div>
    </AppShell>
  )
}
