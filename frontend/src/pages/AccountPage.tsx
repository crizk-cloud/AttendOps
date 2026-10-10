import { useState, type FormEvent } from 'react'
import { api } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { formatDateTime } from '../lib/time'

export function AccountPage() {
  const { user } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    try {
      await api('/api/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: current, new_password: next }),
      })
      setCurrent('')
      setNext('')
      setMsg({ ok: true, text: 'Password changed. Other sessions have been signed out.' })
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : 'Failed' })
    }
  }

  return (
    <section>
      <h2>My account</h2>
      <div className="card">
        <dl className="kv">
          <dt>Email</dt>
          <dd>{user?.email}</dd>
          <dt>Role</dt>
          <dd>{user?.role}</dd>
          <dt>Last login</dt>
          <dd>{formatDateTime(user?.last_login_at)}</dd>
        </dl>
      </div>
      <form className="card narrow" onSubmit={submit}>
        <h3>Change password</h3>
        <label>
          Current password
          <input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
        </label>
        <label>
          New password (min. 10 characters)
          <input type="password" autoComplete="new-password" minLength={10} value={next} onChange={(e) => setNext(e.target.value)} required />
        </label>
        {msg && <div className={msg.ok ? 'success' : 'error'}>{msg.text}</div>}
        <button type="submit">Change password</button>
      </form>
    </section>
  )
}
