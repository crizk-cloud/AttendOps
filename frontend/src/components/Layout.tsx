import { NavLink, Outlet } from 'react-router-dom'
import type { Role } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { APP_TIME_ZONE } from '../lib/time'

const NAV: { to: string; label: string; minRole: Role }[] = [
  { to: '/', label: 'Dashboard', minRole: 'viewer' },
  { to: '/devices', label: 'Manage devices', minRole: 'admin' },
  { to: '/app-users', label: 'App accounts', minRole: 'admin' },
  { to: '/account', label: 'My account', minRole: 'viewer' },
]

export function Layout() {
  const { user, logout, hasRole } = useAuth()
  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">AttendOps</span>
        <nav>
          {NAV.filter((n) => hasRole(n.minRole)).map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === '/'}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <span className="spacer" />
        <span className="muted small">Times: {APP_TIME_ZONE}</span>
        <span className="user">
          {user?.email} <span className={`role role-${user?.role}`}>{user?.role}</span>
        </span>
        <button className="link" onClick={() => void logout()}>
          Log out
        </button>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  )
}
