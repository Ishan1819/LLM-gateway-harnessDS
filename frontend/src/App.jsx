import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'

import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import { Spinner } from './components/Primitives'
import { api, auth } from './services/api'

import Alerts from './pages/Alerts'
import Caps from './pages/Caps'
import Cluster from './pages/Cluster'
import EmployeeSimulator from './pages/EmployeeSimulator'
import Dashboard from './pages/Dashboard'
import Governance from './pages/Governance'
import Login from './pages/Login'
import Optimizer from './pages/Optimizer'
import Plan from './pages/Plan'
import Savings from './pages/Savings'
import Settings from './pages/Settings'
import Teams from './pages/Teams'
import Users from './pages/Users'

const SessionContext = createContext(null)
export const useSession = () => useContext(SessionContext)

export default function App() {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const [unreadAlerts, setUnreadAlerts] = useState(0)
  const navigate = useNavigate()

  useEffect(() => {
    if (!auth.token) {
      setLoading(false)
      return
    }
    api
      .me()
      .then((data) => setSession({ admin: data.admin, organization: data.organization }))
      .catch(() => auth.clear())
      .finally(() => setLoading(false))
  }, [])

  const signIn = useCallback((payload) => {
    auth.token = payload.access_token
    setSession({ admin: payload.admin, organization: payload.organization })
  }, [])

  const signOut = useCallback(() => {
    auth.clear()
    setSession(null)
    navigate('/login')
  }, [navigate])

  const value = useMemo(
    () => ({ ...session, signIn, signOut, setUnreadAlerts, refreshOrg: setSession }),
    [session, signIn, signOut],
  )

  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center bg-page">
        <Spinner label="Restoring session" />
      </div>
    )
  }

  if (!session) {
    return (
      <SessionContext.Provider value={value}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </SessionContext.Provider>
    )
  }

  return (
    <SessionContext.Provider value={value}>
      <div className="flex min-h-screen bg-page">
        <Sidebar
          organization={session.organization}
          admin={session.admin}
          unreadAlerts={unreadAlerts}
          onSignOut={signOut}
        />
        <main className="flex-1 min-w-0 overflow-x-hidden">
          <TopBar
            organization={session.organization}
            admin={session.admin}
            onSignOut={signOut}
          />
          <div className="mx-auto max-w-[1400px] px-8 py-8">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/teams" element={<Teams />} />
              <Route path="/users" element={<Users />} />
              <Route path="/caps" element={<Caps />} />
              <Route path="/alerts" element={<Alerts />} />
              <Route path="/savings" element={<Savings />} />
              <Route path="/optimizer" element={<Optimizer />} />
              <Route path="/governance" element={<Governance />} />
              <Route path="/cluster" element={<Cluster />} />
              <Route path="/simulator" element={<EmployeeSimulator />} />
              <Route path="/plan" element={<Plan />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/login" element={<Navigate to="/" replace />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>
        </main>
      </div>
    </SessionContext.Provider>
  )
}
