import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { ConnectionTestResult, Device } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import { parseBulk } from '../lib/bulkParse'
import { formatRelative } from '../lib/time'
import { useDevices } from '../lib/useDevices'

export function DevicesPage() {
  const { devices, error, reload } = useDevices()
  const [tab, setTab] = useState<'single' | 'bulk'>('single')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  async function remove(d: Device) {
    if (!window.confirm(`Remove "${d.name}" (${d.ip}) from AttendOps?\n\nNothing is changed on the device itself.`)) return
    try {
      await api(`/api/devices/${d.id}`, { method: 'DELETE' })
      setMsg({ ok: true, text: `Removed ${d.name}.` })
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : 'Delete failed' })
    }
    void reload()
  }

  async function toggle(d: Device) {
    await api(`/api/devices/${d.id}`, { method: 'PATCH', body: JSON.stringify({ enabled: !d.enabled }) })
    void reload()
  }

  return (
    <section>
      <h2>Manage devices</h2>
      <p className="muted">
        Register devices with their address and login. Passwords are stored encrypted and are never shown again.
      </p>
      {error && <div className="error">{error}</div>}
      {msg && <div className={msg.ok ? 'success' : 'error'}>{msg.text}</div>}

      <div className="card">
        <div className="tabs">
          <button className={tab === 'single' ? 'tab active' : 'tab'} onClick={() => setTab('single')}>
            Add one device
          </button>
          <button className={tab === 'bulk' ? 'tab active' : 'tab'} onClick={() => setTab('bulk')}>
            Add many devices
          </button>
        </div>
        {tab === 'single' ? (
          <SingleAdd onDone={(t) => { setMsg({ ok: true, text: t }); void reload() }} />
        ) : (
          <BulkAdd onDone={(t) => { setMsg({ ok: true, text: t }); void reload() }} />
        )}
      </div>

      <div className="card">
        <h3>Registered devices ({devices?.length ?? 0})</h3>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Address</th>
              <th>Login user</th>
              <th>Status</th>
              <th>Last contact</th>
              <th>Enabled</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {devices?.map((d) => (
              <tr key={d.id} className={d.enabled ? '' : 'inactive'}>
                <td>
                  <Link to={`/devices/${d.id}`}>{d.name}</Link>
                </td>
                <td className="mono">
                  {d.ip}:{d.port}
                </td>
                <td>{d.username}</td>
                <td>
                  <StatusBadge status={d.status} checking={d.checking} />
                </td>
                <td>{formatRelative(d.last_seen_at)}</td>
                <td>
                  <input type="checkbox" checked={d.enabled} onChange={() => void toggle(d)} title="Include in checks and sync" />
                </td>
                <td className="actions">
                  <Link to={`/devices/${d.id}`}>Edit</Link>
                  <button className="link danger" onClick={() => void remove(d)}>
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function TestResult({ r }: { r: ConnectionTestResult }) {
  return (
    <div className={r.status === 'online' ? 'success' : 'error'}>
      <StatusBadge status={r.status} />{' '}
      {r.status === 'online'
        ? `Connected in ${r.response_ms} ms. Model: ${r.model ?? 'unknown'}, firmware: ${r.firmware ?? 'unknown'}`
        : r.error}
    </div>
  )
}

function SingleAdd({ onDone }: { onDone: (msg: string) => void }) {
  const empty = { name: '', ip: '', port: 80, username: 'admin', password: '', notes: '' }
  const [f, setF] = useState(empty)
  const [test, setTest] = useState<ConnectionTestResult | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true)
    setErr(null)
    try {
      return await fn()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Request failed')
    } finally {
      setBusy(false)
    }
  }

  const testConn = () =>
    run(async () =>
      setTest(
        await api<ConnectionTestResult>('/api/devices/test-connection', {
          method: 'POST',
          body: JSON.stringify({ ip: f.ip, port: f.port, username: f.username, password: f.password }),
        }),
      ),
    )

  async function submit(e: FormEvent) {
    e.preventDefault()
    const d = await run(() =>
      api<Device>('/api/devices', { method: 'POST', body: JSON.stringify({ ...f, notes: f.notes || null }) }),
    )
    if (d) {
      setF(empty)
      setTest(null)
      onDone(`Added ${d.name}: ${d.status === 'online' ? `online (${d.model ?? 'model unknown'})` : `saved, but ${d.last_error ?? d.status}`}.`)
    }
  }

  return (
    <form onSubmit={submit} className="grid-form">
      <label>
        Name
        <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Main entrance" required />
      </label>
      <label>
        IP address
        <input value={f.ip} onChange={(e) => setF({ ...f, ip: e.target.value })} placeholder="172.22.76.12" required />
      </label>
      <label>
        Port
        <input type="number" min={1} max={65535} value={f.port} onChange={(e) => setF({ ...f, port: Number(e.target.value) })} />
      </label>
      <label>
        Device username
        <input value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} autoComplete="off" required />
      </label>
      <label>
        Device password
        <input type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} autoComplete="new-password" required />
      </label>
      <label>
        Notes
        <input value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} placeholder="optional" />
      </label>
      <div className="full">
        {test && <TestResult r={test} />}
        {err && <div className="error">{err}</div>}
        <div className="row">
          <button type="button" className="secondary" disabled={busy || !f.ip || !f.username || !f.password} onClick={() => void testConn()}>
            Test connection
          </button>
          <button type="submit" disabled={busy}>
            {busy ? 'Working…' : 'Add device'}
          </button>
        </div>
      </div>
    </form>
  )
}

function BulkAdd({ onDone }: { onDone: (msg: string) => void }) {
  const [text, setText] = useState('')
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const lines = parseBulk(text)
  const invalid = lines.filter((l) => l.error)
  const missingCreds = lines.filter((l) => !l.error && !l.password && !password)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    try {
      const r = await api<{ created: number[]; skipped: { ip: string; reason: string }[] }>('/api/devices/bulk', {
        method: 'POST',
        body: JSON.stringify({
          default_username: username || null,
          default_password: password || null,
          devices: lines.map(({ ip, port, name, username, password }) => ({ ip, port, name, username, password })),
        }),
      })
      const skipped = r.skipped.map((s) => `${s.ip} (${s.reason})`).join(', ')
      onDone(`Added ${r.created.length} device(s); they are being checked now.${skipped ? ` Skipped: ${skipped}.` : ''}`)
      setText('')
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Bulk add failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit}>
      <p className="muted small">
        One device per line: <code>ip[:port], name, username, password</code>. Name and login are optional; lines
        without a login use the shared login below.
      </p>
      <textarea
        rows={10}
        value={text}
        onChange={(e) => setText(e.target.value)}
        spellCheck={false}
        placeholder={'172.22.76.12, Main entrance\n172.22.76.13, Staff door\n172.23.5.202, Annex gate, admin, other-password'}
      />
      <div className="grid-form">
        <label>
          Shared device username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" />
        </label>
        <label>
          Shared device password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
        </label>
      </div>
      {lines.length > 0 && (
        <table className="preview">
          <thead>
            <tr>
              <th>Line</th>
              <th>Address</th>
              <th>Name</th>
              <th>Login</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => (
              <tr key={l.line} className={l.error ? 'bad' : ''}>
                <td>{l.line}</td>
                <td className="mono">
                  {l.ip}:{l.port}
                </td>
                <td>{l.name ?? l.ip}</td>
                <td>{l.password ? `own login (${l.username})` : 'shared login'}</td>
                <td className="small">{l.error}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {invalid.length > 0 && <div className="error">Fix {invalid.length} invalid line(s) before adding.</div>}
      {missingCreds.length > 0 && <div className="error">Enter a shared password, or give each line its own login.</div>}
      {err && <div className="error">{err}</div>}
      <button type="submit" disabled={busy || !lines.length || invalid.length > 0 || missingCreds.length > 0}>
        {busy ? 'Adding…' : `Add ${lines.length || ''} device(s)`}
      </button>
    </form>
  )
}
