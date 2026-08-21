import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import ProtectedRoute from './components/auth/ProtectedRoute'
import RequireAdmin from './components/auth/RequireAdmin'
import ReportingOnlyGuard from './components/auth/ReportingOnlyGuard'
import FranchiseUsersPage from './pages/franchise/FranchiseUsersPage'
import LoginPage from './pages/LoginPage'
import SetPasswordPage from './pages/SetPasswordPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import PrivacyPolicyPage from './pages/PrivacyPolicyPage'
import HelpPage from './pages/HelpPage'
import ProfilePage from './pages/ProfilePage'
import StudioManagerPage from './pages/StudioManagerPage'
import OwnerBillingPage from './pages/billing/OwnerBillingPage'
import OnboardPage from './pages/OnboardPage'
import SharedDeviceLoginPage from './pages/SharedDeviceLoginPage'
import ExistingStudiosPage from './pages/ExistingStudiosPage'
import HomePage from './pages/HomePage'
import UsersPage from './pages/admin/UsersPage'
import SetupDashboardPage from './pages/setup/SetupDashboardPage'
import OwnershipDashboardPage from './pages/ownership/OwnershipDashboardPage'
import StudiosPage from './pages/ownership/StudiosPage'
import FranchiseFormPage from './pages/ownership/FranchiseFormPage'
import FranchisesListPage from './pages/ownership/FranchisesListPage'
import StudioOwnersPage from './pages/ownership/StudioOwnersPage'
import FranchiseOwnersPage from './pages/ownership/FranchiseOwnersPage'
import FranchiseStudiosPage from './pages/ownership/FranchiseStudiosPage'
import OwnershipScopePage from './pages/ownership/OwnershipScopePage'
import NotesPage from './pages/NotesPage'
import ChatPage from './pages/ChatPage'
import QuestionsPage from './pages/admin/QuestionsPage'
import LoginLogPage from './pages/admin/LoginLogPage'
import StudioAssignmentPage from './pages/admin/StudioAssignmentPage'
import BillingPage from './pages/setup/BillingPage'
import PricingTiersPage from './pages/setup/PricingTiersPage'
import DevBadge from './components/layout/DevBadge'

export default function App() {
  // basename follows vite's `base` so the app works at the root AND under a
  // path mount. Without it the router treats a mounted path as an unmatched
  // route and navigates to "/", which is the dev index — the app appeared to
  // bounce back to the index on every page load.
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      {/* Dev only: says which branch and commit this server is actually
          serving. See DevBadge for why a port number is not enough. */}
      <DevBadge />
      <ReportingOnlyGuard />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/set-password" element={<SetPasswordPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        {/* PUBLIC by design — a privacy-policy URL that's reachable without
            signing in, so this must stay outside ProtectedRoute. Both
            spellings are routed because either may already be linked
            externally. */}
        <Route path="/privacy" element={<PrivacyPolicyPage />} />
        <Route path="/privacy-policy" element={<PrivacyPolicyPage />} />
        <Route
          path="/help"
          element={
            <ProtectedRoute>
              <HelpPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <ProfilePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/studio-manager"
          element={
            <ProtectedRoute>
              <StudioManagerPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/billing"
          element={
            <ProtectedRoute>
              <OwnerBillingPage />
            </ProtectedRoute>
          }
        />
        <Route path="/onboard" element={<OnboardPage />} />
        <Route path="/shared" element={<SharedDeviceLoginPage />} />
        {/* PUBLIC by design — the studio code is entered here BEFORE
            anyone can sign in, so a login gate would be a closed loop. */}
        <Route path="/existing-studios" element={<ExistingStudiosPage />} />
        <Route
          path="/admin/overview"
          element={
            <ProtectedRoute>
              <HomePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/users"
          element={
            <ProtectedRoute>
              <UsersPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/studios"
          element={
            <ProtectedRoute>
              <StudiosPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/setup"
          element={
            <ProtectedRoute>
              <SetupDashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/import"
          element={<Navigate to="/admin/overview" replace />}
        />
        <Route
          path="/setup/billing"
          element={
            <ProtectedRoute>
              <RequireAdmin>
                <BillingPage />
              </RequireAdmin>
            </ProtectedRoute>
          }
        />
        <Route
          path="/setup/pricing-tiers"
          element={
            <ProtectedRoute>
              <RequireAdmin>
                <PricingTiersPage />
              </RequireAdmin>
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/studio-assignment"
          element={
            <ProtectedRoute>
              <RequireAdmin>
                <StudioAssignmentPage />
              </RequireAdmin>
            </ProtectedRoute>
          }
        />
        <Route
          path="/notes"
          element={
            <ProtectedRoute>
              <NotesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/chat"
          element={
            <ProtectedRoute>
              <ChatPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/questions"
          element={
            <ProtectedRoute>
              <RequireAdmin>
                <QuestionsPage />
              </RequireAdmin>
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/login-log"
          element={
            <ProtectedRoute>
              <RequireAdmin>
                <LoginLogPage />
              </RequireAdmin>
            </ProtectedRoute>
          }
        />
        <Route
          path="/ownership"
          element={
            <ProtectedRoute>
              <RequireAdmin>
                <OwnershipDashboardPage />
              </RequireAdmin>
            </ProtectedRoute>
          }
        />
        <Route
          path="/ownership/studio-owners"
          element={
            <ProtectedRoute>
              <RequireAdmin>
                <StudioOwnersPage />
              </RequireAdmin>
            </ProtectedRoute>
          }
        />
        <Route
          path="/ownership/franchises"
          element={
            <ProtectedRoute>
              <RequireAdmin>
                <FranchisesListPage />
              </RequireAdmin>
            </ProtectedRoute>
          }
        />
        <Route
          path="/ownership/franchises/new"
          element={
            <ProtectedRoute>
              <RequireAdmin>
                <FranchiseFormPage />
              </RequireAdmin>
            </ProtectedRoute>
          }
        />
        <Route
          path="/ownership/franchises/:franchiseId"
          element={
            <ProtectedRoute>
              <RequireAdmin>
                <FranchiseFormPage />
              </RequireAdmin>
            </ProtectedRoute>
          }
        />
        <Route
          path="/ownership/franchise-owners"
          element={
            <ProtectedRoute>
              <RequireAdmin>
                <FranchiseOwnersPage />
              </RequireAdmin>
            </ProtectedRoute>
          }
        />
        <Route
          path="/ownership/franchise-studios"
          element={
            <ProtectedRoute>
              <RequireAdmin>
                <FranchiseStudiosPage />
              </RequireAdmin>
            </ProtectedRoute>
          }
        />
        <Route
          path="/ownership/scope"
          element={
            <ProtectedRoute>
              <OwnershipScopePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/franchise/users"
          element={
            <ProtectedRoute>
              <FranchiseUsersPage />
            </ProtectedRoute>
          }
        />
        <Route path="/admin" element={<Navigate to="/admin/overview" replace />} />
        <Route path="/" element={<Navigate to="/admin/overview" replace />} />
        <Route path="*" element={<Navigate to="/admin/overview" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
