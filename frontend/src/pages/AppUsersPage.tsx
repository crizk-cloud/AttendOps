import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import type { AppUser, Role } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { formatDateTime } from '../lib/time'

const ROLES: Role[] = ['viewer', 'operator', 'admin']

export function AppUsersPage() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState<AppUser[]>([])
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({ email: '', full_name: '', password: '', role: 'viewer' as Role })

  const load = useCallback(() => {
    api<AppUser[]>('/api/app-users').then(setUsers, (e: Error) => setError(e.message))
  }, [])
  useEffect(load, [load])

  async function update(id: number, patch: Partial<Pick<AppUser, 'role' | 'is_active'>>) {
    setError(null)
    try {
      await api(`/api/app-users/${id}`, { method: 'PATCH', body: JSON.stringify(patch) })
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Update failed')
    }
  }

  async function create(e: FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      await api('/api/app-users', { method: 'POST', body: JSON.stringify({ ...form, full_name: form.full_name || null }) })
      setForm({ email: '', full_name: '', password: '', role: 'viewer' })
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Create failed')
    }
  }

  return (
    <section>
      <h2>App accounts</h2>
      <p className="muted">People who can sign in to this web app. These are not device users.</p>
      {error && <div className="error">{error}</div>}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Email</th>
              <th>Name</th>
              <th>Role</th>
              <th>Active</th>
              <th>Last login</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className={u.is_active ? '' : 'inactive'}>
                <td>{u.email}</td>
                <td>{u.full_name ?? '—'}</td>
                <td>
                  <select value={u.role} onChange={(e) => void update(u.id, { role: e.target.value as Role })}>
                    {ROLES.map((r) => (
                      <option key={r}>{r}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={u.is_active}
                    disabled={u.id === me?.id}
                    title={u.id === me?.id ? 'You cannot disable your own account' : ''}
                    onChange={(e) => void update(u.id, { is_active: e.target.checked })}
                  />
                </td>
                <td>{formatDateTime(u.last_login_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form className="card narrow" onSubmit={create}>
        <h3>Add account</h3>
        <label>
          Email
          <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
        </label>
        <label>
          Full name
          <input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        </label>
        <label>
          Initial password (min. 10 characters)
          <input
            type="password"
            autoComplete="new-password"
            minLength={10}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            required
          />
        </label>
        <label>
          Role
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
            {ROLES.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </label>
        <button type="submit">Create account</button>
      </form>
    </section>
  )
}
