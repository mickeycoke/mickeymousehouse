import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

/**
 * `signInPath` defaults to the business login, so every existing route
 * behaves exactly as it did. Coach passes its own door: a member who signs
 * out - or whose token expires mid-workout - belongs on the screen they know,
 * and must not be shown the studio's login, which is not their product.
 */
export default function ProtectedRoute({ children, signInPath = '/login' }) {
  const { isAuthenticated, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to={signInPath} replace state={{ from: location }} />
  }

  return children
}
