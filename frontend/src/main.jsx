import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'
import App from './App'
import { AuthProvider } from './context/AuthContext'
import { StudioProvider } from './context/StudioContext'
import { FranchiseProvider } from './context/FranchiseContext'

// Tells index.html's load watchdog the bundle parsed and React took over —
// the "page never finished loading" banner only fires when this never runs.
window.__ptMounted = true

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AuthProvider>
      <FranchiseProvider>
        <StudioProvider>
          <App />
        </StudioProvider>
      </FranchiseProvider>
    </AuthProvider>
  </React.StrictMode>
)
