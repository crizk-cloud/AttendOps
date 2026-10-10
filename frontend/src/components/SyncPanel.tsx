import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import type { Device, SyncRun } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { addDays, formatDateTime, formatRelative, localDate } from '../lib/time'
import { SourceTag } from './SourceTag'
import { SyncBadge } from './SyncBadge'

export function SyncPanel({ device, onChange }: { device: Device; onChange: () => void }) {
  const { hasRole } = useAuth()
  const [runs, setRuns] = useState<SyncRun[]>([])
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [range, setRange] = useState({ start_date: addDays(localDate(), -30), end_date: localDate() })

  const loadRuns = useCallback(() => {
    api<SyncRun[]>(`/api/sync/runs?device_id=${device.id}&limit=10`).then(setRuns, () => {})
  }, [device.id])

  // Refresh while a sync is running.
  useEffect(() => {
    loadRuns()
    if (!device.syncing) return
    const t = window.setInterval(() => {
      loadRuns()
      onChange()
    }, 2000)
    return () => window.clearInterval(t)
  }, [device.syncing, loadRuns, onChange])

  async function start(body?: object) {
    setMsg(null)
    try {
      await api(`/api/devices/${device.id}/sync`, { method: 'POST', body: body ? JSON.stringify(body) : undefined })
      setMsg({ ok: true, text: 'Sync started.' })
      onChange()
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : 'Failed to start sync' })
    }
  }

  function reimport(e: FormEvent) {
    e.preventDefault()
    void start(range)
  }

  return (
    <div className="card">
      <div className="page-head">
        <h3>
          Access history sync <SourceTag source="observed" />
        </h3>
        {hasRole('operator') && (
          <button disabled={device.syncing || !device.enabled} onClick={() => void start()}>
            {device.syncing ? 'Syncing…' : 'Sync now'}
          </button>
        )}
      </div>
      <dl className="kv">
        <dt>Last sync</dt>
        <dd>
          <SyncBadge status={device.last_sync_status} syncing={device.syncing} />{' '}
          {device.last_sync_at && <span className="muted">{formatRelative(device.last_sync_at)}</span>}
        </dd>
        <dt>Imported up to</dt>
        <dd>{device.synced_until ? formatDateTime(device.synced_until) : 'nothing yet (first sync imports the last 30 days)'}</dd>
      </dl>
      {msg && <div className={msg.ok ? 'success' : 'error'}>{msg.text}</div>}

      {hasRole('operator') && (
        <form className="row reimport" onSubmit={reimport}>
          <span className="muted small">Re-import a date range (safe: existing records are not duplicated):</span>
          <input type="date" value={range.start_date} max={range.end_date} onChange={(e) => setRange({ ...range, start_date: e.target.value })} />
          <span>to</span>
          <input type="date" value={range.end_date} min={range.start_date} onChange={(e) => setRange({ ...range, end_date: e.target.value })} />
          <button className="secondary" type="submit" disabled={device.syncing}>
            Re-import
          </button>
        </form>
      )}

      <h4>Recent runs</h4>
      {runs.length === 0 ? (
        <p className="muted">No sync runs yet.</p>
      ) : (
        <table className="small-table">
          <thead>
            <tr>
              <th>Started</th>
              <th>Status</th>
              <th>Window</th>
              <th title="Records the device returned">Found</th>
              <th title="New records stored">New</th>
              <th>Queries</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id}>
                <td className="nowrap">{formatDateTime(r.started_at)}</td>
                <td>
                  <SyncBadge status={r.status} />
                </td>
                <td className="small nowrap">
                  {formatDateTime(r.window_start).slice(0, 10)} → {formatDateTime(r.window_end).slice(0, 10)}
                </td>
                <td>{r.records_found}</td>
                <td>{r.records_inserted}</td>
                <td>{r.queries}</td>
                <td className="small">
                  {r.error_message && <div className="danger-text">{r.error_message}</div>}
                  {r.warnings?.length ? <div className="muted">{r.warnings.length} warning(s)</div> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
