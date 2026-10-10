import { useAuth } from '../auth/AuthContext'

export function DashboardPage() {
  const { user } = useAuth()
  return (
    <section>
      <h2>Dashboard</h2>
      <div className="card">
        <p>
          Signed in as <strong>{user?.email}</strong> ({user?.role}).
        </p>
        <p className="muted">Device registration and online/offline status arrive in Phase 2.</p>
      </div>
    </section>
  )
}
