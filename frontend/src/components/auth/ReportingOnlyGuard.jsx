import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

// UI-only lockdown for the franchise reporting persona: they may reach only
// Home and their profile — plus, for OWNERS, the franchise-users page. Any
// other route bounces to Home. Centralized so no sensitive route can be
// missed. (Backend API 403-enforcement is a separate, later phase.)
const PUBLIC = ['/login', '/set-password', '/onboard', '/shared', '/existing-studios']

export default function ReportingOnlyGuard() {
  const { myRoles } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => {
    if (!myRoles?.franchise_reporting_only) return
    const allowed = ['/admin/overview', '/profile', ...PUBLIC]
    if (myRoles.franchise_can_invite) allowed.push('/franchise/users')
    const path = location.pathname
    const ok = allowed.some(
      (p) => path === p || path.startsWith(p.endsWith('/') ? p : `${p}/`)
    )
    if (!ok) navigate('/admin/overview', { replace: true })
  }, [myRoles, location.pathname, navigate])

  return null
}
