import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import type { Role } from '../api/types'
import { useAuth } from './AuthContext'

// UI-side guard only, for navigation. The backend enforces every role check independently.
export function RequireAuth({ minRole = 'viewer', children }: { minRole?: Role; children: ReactNode }) {
  const { user, loading, hasRole } = useAuth()
  const location = useLocation()
  if (loading) return <div className="page-loading">Loading…</div>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (!hasRole(minRole)) return <div className="card">You need the “{minRole}” role to view this page.</div>
  return <>{children}</>
}
