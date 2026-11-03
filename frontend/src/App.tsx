import { useQuery, useQueryClient } from '@tanstack/react-query'
import { MotionConfig } from 'framer-motion'
import { Award, BarChart3, CalendarRange, IndianRupee, LayoutDashboard, LogOut, MonitorPlay, Users, Zap, ZapOff } from 'lucide-react'
import { useEffect } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { api } from './api'
import { ConfirmProvider, Loading, ToastProvider } from './components/ui'
import { setReducedMotion, useReducedMotion } from './lib/prefs'
import Arena from './pages/Arena'
import Awards from './pages/Awards'
import BDPerformance, { BDIndex } from './pages/BDPerformance'
import Dashboard from './pages/Dashboard'
import DemoTracker from './pages/DemoTracker'
import Login from './pages/Login'
import Reports from './pages/Reports'
import RevenueTracker from './pages/RevenueTracker'

function Brand() {
  return (
    <NavLink to="/" className="brand" aria-label="FireFlink League home">
      <img src="/fireflink-logo.svg" className="brand-mark" alt="" />
      <div>
        <div className="brand-word">FIREFLINK</div>
        <div className="brand-sub">4.0 League</div>
      </div>
    </NavLink>
  )
}

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/bd', label: 'BD Performance', icon: Users },
  { to: '/demos', label: 'Demo Tracker', icon: CalendarRange },
  { to: '/revenue', label: 'Revenue Tracker', icon: IndianRupee },
  { to: '/awards', label: 'Awards', icon: Award },
  { to: '/reports', label: 'Reports & Settings', icon: BarChart3 },
]

function Shell({ user }: { user: string }) {
  const qc = useQueryClient()
  const { active, setting } = useReducedMotion()
  const logout = async () => {
    await api.post('/api/auth/logout')
    qc.clear()
    window.location.href = '/login'
  }
  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <Brand />
          <nav className="nav" aria-label="Main">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} title={n.label}>
                <n.icon size={17} /> <span className="label">{n.label}</span>
              </NavLink>
            ))}
          </nav>
          <div className="topbar-actions">
            <button className="btn ghost icon sm" title={active ? 'Reduced motion is on — click for full animations' : 'Animations on — click for reduced motion'}
              aria-label="Toggle reduced motion" onClick={() => setReducedMotion(active ? 'off' : 'on')}>
              {active ? <ZapOff size={16} /> : <Zap size={16} />}
            </button>
            <a className="btn sm" href="/arena" target="_blank" rel="noreferrer" title="Open League Arena (office display)">
              <MonitorPlay size={15} /> <span className="hide-sm">League Arena</span>
            </a>
            <button className="btn sm primary" onClick={logout} title={`Signed in as ${user}${setting === 'system' ? ' · motion follows system setting' : ''} — sign out`}><LogOut size={14} /> <span className="hide-sm">Sign out</span></button>
          </div>
        </div>
      </header>
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/bd" element={<BDIndex />} />
          <Route path="/bd/:id" element={<BDPerformance />} />
          <Route path="/demos" element={<DemoTracker />} />
          <Route path="/revenue" element={<RevenueTracker />} />
          <Route path="/awards" element={<Awards />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  const loc = useLocation()
  const { active } = useReducedMotion()
  const isArena = loc.pathname.startsWith('/arena')
  const me = useQuery({ queryKey: ['me'], queryFn: () => api.get<{ username: string }>('/api/auth/me'), retry: false, enabled: !isArena })

  useEffect(() => {
    const h = () => { if (!location.pathname.startsWith('/login') && !location.pathname.startsWith('/arena')) location.href = '/login' }
    window.addEventListener('ffl:unauthorized', h)
    return () => window.removeEventListener('ffl:unauthorized', h)
  }, [])

  let body
  if (isArena) body = <Arena />
  else if (loc.pathname === '/login') body = me.data ? <Navigate to="/" replace /> : <Login />
  else if (me.isLoading) body = <Loading />
  else if (!me.data) body = <Navigate to="/login" replace />
  else body = <Shell user={me.data.username} />

  return (
    <MotionConfig reducedMotion={active ? 'always' : 'never'}>
      <ToastProvider>
        <ConfirmProvider>{body}</ConfirmProvider>
      </ToastProvider>
    </MotionConfig>
  )
}
