import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Device, DeviceStatus } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { StatusBadge } from '../components/StatusBadge'
import { formatDateTime, formatRelative } from '../lib/time'
import { useDevices } from '../lib/useDevices'

const TILES: { status: DeviceStatus; label: string }[] = [
  { status: 'online', label: 'Online' },
  { status: 'offline', label: 'Offline' },
  { status: 'auth_failed', label: 'Login failed' },
  { status: 'error', label: 'Error' },
  { status: 'unknown', label: 'Not checked' },
]

export function DashboardPage() {
  const { hasRole } = useAuth()
  const { devices, error, reload } = useDevices()
  const [busy, setBusy] = useState<number | 'all' | null>(null)
  const [filter, setFilter] = useState<DeviceStatus | null>(null)
  const canCheck = hasRole('operator')

  async function checkAll() {
    setBusy('all')
    try {
      await api('/api/devices/check-all', { method: 'POST' })
    } finally {
      setBusy(null)
      void reload()
    }
  }

  async function checkOne(d: Device) {
    setBusy(d.id)
    try {
      await api(`/api/devices/${d.id}/check`, { method: 'POST' })
    } finally {
      setBusy(null)
      void reload()
    }
  }

  const enabled = devices?.filter((d) => d.enabled) ?? []
  const shown = (devices ?? []).filter((d) => !filter || d.status === filter)
  const anyChecking = devices?.some((d) => d.checking)

  return (
    <section>
      <div className="page-head">
        <h2>Dashboard</h2>
        {canCheck && (
          <button onClick={() => void checkAll()} disabled={busy !== null || anyChecking || !enabled.length}>
            {anyChecking ? 'Checking…' : 'Check all devices'}
          </button>
        )}
      </div>
      {error && <div className="error">{error}</div>}

      <div className="tiles">
        <button className={`tile ${filter === null ? 'active' : ''}`} onClick={() => setFilter(null)}>
          <span className="tile-num">{enabled.length}</span>
          <span className="tile-label">Devices</span>
        </button>
        {TILES.map((t) => (
          <button
            key={t.status}
            className={`tile tile-${t.status} ${filter === t.status ? 'active' : ''}`}
            onClick={() => setFilter(filter === t.status ? null : t.status)}
          >
            <span className="tile-num">{enabled.filter((d) => d.status === t.status).length}</span>
            <span className="tile-label">{t.label}</span>
          </button>
        ))}
      </div>

      <div className="card">
        {devices === null ? (
          <p className="muted">Loading…</p>
        ) : devices.length === 0 ? (
          <p className="muted">
            No devices registered yet.{' '}
            {hasRole('admin') ? <Link to="/devices">Add devices</Link> : 'Ask an admin to add devices.'}
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Device</th>
                <th>Address</th>
                <th>Status</th>
                <th title="Last time the device answered an authenticated request">Last successful contact</th>
                <th>Last check</th>
                <th title="Reported by the device">Model / firmware</th>
                {canCheck && <th />}
              </tr>
            </thead>
            <tbody>
              {shown.map((d) => (
                <tr key={d.id} className={d.enabled ? '' : 'inactive'}>
                  <td>
                    <Link to={`/devices/${d.id}`}>{d.name}</Link>
                    {!d.enabled && <span className="muted small"> (disabled)</span>}
                  </td>
                  <td className="mono">
                    {d.ip}
                    {d.port !== 80 && `:${d.port}`}
                  </td>
                  <td>
                    <StatusBadge status={d.status} checking={d.checking || busy === d.id} />
                    {d.last_error && d.status !== 'online' && <div className="small muted">{d.last_error}</div>}
                  </td>
                  <td title={formatDateTime(d.last_seen_at)}>{formatRelative(d.last_seen_at)}</td>
                  <td title={formatDateTime(d.last_checked_at)}>{formatRelative(d.last_checked_at)}</td>
                  <td className="small">
                    {d.model ?? <span className="muted">unknown</span>}
                    {d.firmware && <div className="muted">{d.firmware}</div>}
                  </td>
                  {canCheck && (
                    <td>
                      <button className="secondary" disabled={busy !== null || d.checking} onClick={() => void checkOne(d)}>
                        Check
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <p className="muted small">Status refreshes automatically. Times are shown in Asia/Beirut.</p>
    </section>
  )
}
