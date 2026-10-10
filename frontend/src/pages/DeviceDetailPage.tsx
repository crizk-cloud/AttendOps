import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { ConnectionTestResult, Device } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { SourceTag } from '../components/SourceTag'
import { StatusBadge } from '../components/StatusBadge'
import { formatDateTime, formatRelative } from '../lib/time'

const OPERATION_LABELS: Record<string, string> = {
  'device.info': 'Read model / firmware',
  'history.read': 'Read access history',
  'events.subscribe': 'Live event stream',
  'users.read': 'Read users (AccessUser API)',
  'cards.read': 'Read cards (AccessCard API)',
  'cards.read_legacy': 'Read cards (legacy record API)',
  'users.write': 'Create / update / delete users',
  'cards.write': 'Create / update / delete cards',
}

const OPERATION_ORDER = Object.keys(OPERATION_LABELS)

export function DeviceDetailPage() {
  const { id } = useParams()
  const { hasRole } = useAuth()
  const [d, setD] = useState<Device | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api<Device>(`/api/devices/${id}`).then(setD, (e: Error) => setErr(e.message))
  }, [id])
  useEffect(load, [load])

  async function action(path: string) {
    setBusy(true)
    setErr(null)
    try {
      setD(await api<Device>(`/api/devices/${id}/${path}`, { method: 'POST' }))
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed')
    } finally {
      setBusy(false)
    }
  }

  if (!d) return <section>{err ? <div className="error">{err}</div> : <p className="muted">Loading…</p>}</section>

  return (
    <section>
      <p className="small">
        <Link to="/">← Dashboard</Link>
      </p>
      <div className="page-head">
        <h2>
          {d.name} <StatusBadge status={d.status} checking={busy} />
        </h2>
        <div className="row">
          {hasRole('operator') && (
            <button className="secondary" disabled={busy} onClick={() => void action('check')}>
              Check now
            </button>
          )}
          {hasRole('admin') && (
            <button className="secondary" disabled={busy} onClick={() => void action('detect')} title="Read-only probes">
              Re-detect capabilities
            </button>
          )}
        </div>
      </div>
      {err && <div className="error">{err}</div>}

      <div className="cols">
        <div className="card">
          <h3>
            Connection <SourceTag source="observed" />
          </h3>
          <dl className="kv">
            <dt>Status</dt>
            <dd>
              <StatusBadge status={d.status} />
            </dd>
            <dt>Last successful contact</dt>
            <dd>
              {formatDateTime(d.last_seen_at)} <span className="muted">({formatRelative(d.last_seen_at)})</span>
            </dd>
            <dt>Last check</dt>
            <dd>{formatDateTime(d.last_checked_at)}</dd>
            <dt>Response time</dt>
            <dd>{d.last_response_ms != null ? `${d.last_response_ms} ms` : '—'}</dd>
            <dt>Last error</dt>
            <dd>{d.last_error ?? '—'}</dd>
          </dl>
        </div>
        <div className="card">
          <h3>
            Identity <SourceTag source="device" />
          </h3>
          <dl className="kv">
            <dt>Model</dt>
            <dd>{d.model ?? '—'}</dd>
            <dt>Firmware</dt>
            <dd>{d.firmware ?? '—'}</dd>
            <dt>Serial number</dt>
            <dd className="mono">{d.serial_no ?? '—'}</dd>
          </dl>
        </div>
      </div>

      <div className="card">
        <h3>
          Supported operations <SourceTag source="observed" />
        </h3>
        <p className="muted small">
          Detected with read-only requests{d.capabilities_checked_at ? ` on ${formatDateTime(d.capabilities_checked_at)}` : ''}. Write
          operations are never tested automatically, so they stay “unverified” until confirmed manually.
        </p>
        {d.capabilities ? (
          <table>
            <tbody>
              {Object.entries(d.capabilities)
                .sort(([a], [b]) => OPERATION_ORDER.indexOf(a) - OPERATION_ORDER.indexOf(b))
                .map(([op, c]) => (
                <tr key={op}>
                  <td>{OPERATION_LABELS[op] ?? op}</td>
                  <td>
                    <span className={`badge cap-${c.state}`}>{c.state}</span>
                  </td>
                  <td className="small muted">{c.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">Not detected yet. The device must be online once.</p>
        )}
      </div>

      {hasRole('admin') ? <EditDevice key={d.id} device={d} onSaved={setD} /> : <ConfigView d={d} />}
    </section>
  )
}

function ConfigView({ d }: { d: Device }) {
  return (
    <div className="card">
      <h3>
        Configuration <SourceTag source="app" />
      </h3>
      <dl className="kv">
        <dt>Address</dt>
        <dd className="mono">
          {d.ip}:{d.port}
        </dd>
        <dt>Enabled</dt>
        <dd>{d.enabled ? 'yes' : 'no'}</dd>
        <dt>Notes</dt>
        <dd>{d.notes ?? '—'}</dd>
      </dl>
    </div>
  )
}

function EditDevice({ device, onSaved }: { device: Device; onSaved: (d: Device) => void }) {
  const [f, setF] = useState(() => ({
    name: device.name,
    ip: device.ip,
    port: device.port,
    username: device.username ?? '',
    password: '',
    notes: device.notes ?? '',
    enabled: device.enabled,
  }))
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [test, setTest] = useState<ConnectionTestResult | null>(null)
  const [busy, setBusy] = useState(false)

  async function testConn() {
    setBusy(true)
    try {
      setTest(
        await api<ConnectionTestResult>('/api/devices/test-connection', {
          method: 'POST',
          body: JSON.stringify({ device_id: device.id, ip: f.ip, port: f.port, username: f.username, password: f.password || null }),
        }),
      )
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : 'Test failed' })
    } finally {
      setBusy(false)
    }
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setMsg(null)
    try {
      const body = { ...f, password: f.password || undefined, notes: f.notes || null }
      const d = await api<Device>(`/api/devices/${device.id}`, { method: 'PATCH', body: JSON.stringify(body) })
      onSaved(d)
      setF({ ...f, password: '' })
      setMsg({ ok: true, text: 'Saved.' })
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : 'Save failed' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card" onSubmit={save}>
      <h3>
        Configuration <SourceTag source="app" />
      </h3>
      <div className="grid-form">
        <label>
          Name
          <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required />
        </label>
        <label>
          IP address
          <input value={f.ip} onChange={(e) => setF({ ...f, ip: e.target.value })} required />
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
          <input
            type="password"
            value={f.password}
            placeholder="•••••• (unchanged)"
            onChange={(e) => setF({ ...f, password: e.target.value })}
            autoComplete="new-password"
          />
        </label>
        <label>
          Notes
          <input value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />
        </label>
        <label className="inline">
          <input type="checkbox" checked={f.enabled} onChange={(e) => setF({ ...f, enabled: e.target.checked })} />
          Enabled (included in checks and sync)
        </label>
      </div>
      {test && (
        <div className={test.status === 'online' ? 'success' : 'error'}>
          <StatusBadge status={test.status} /> {test.status === 'online' ? `Connected (${test.model ?? 'model unknown'})` : test.error}
        </div>
      )}
      {msg && <div className={msg.ok ? 'success' : 'error'}>{msg.text}</div>}
      <div className="row">
        <button type="button" className="secondary" disabled={busy} onClick={() => void testConn()}>
          Test connection
        </button>
        <button type="submit" disabled={busy}>
          Save changes
        </button>
      </div>
    </form>
  )
}
