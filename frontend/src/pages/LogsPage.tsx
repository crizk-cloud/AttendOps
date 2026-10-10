import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import type { AccessLogDetail, Device, LogPage } from '../api/types'
import { SourceTag } from '../components/SourceTag'
import { addDays, formatDateTime, localDate } from '../lib/time'

const PAGE_SIZES = [25, 50, 100, 200]

function methodLabel(m: number | null): string {
  if (m === null) return '—'
  return m === 1 ? 'Card' : `Method ${m}` // only Method=1 (card) has been confirmed on the devices
}

export function LogsPage() {
  const [params, setParams] = useSearchParams()
  const today = localDate()
  const f = {
    date_from: params.get('date_from') ?? addDays(today, -6),
    date_to: params.get('date_to') ?? today,
    device_id: params.get('device_id') ?? '',
    q: params.get('q') ?? '',
    type: params.get('type') ?? '',
    result: params.get('result') ?? '',
    sort: params.get('sort') ?? 'desc',
    page: Number(params.get('page') ?? 1),
    page_size: Number(params.get('page_size') ?? 50),
  }
  const [search, setSearch] = useState(f.q)
  const [data, setData] = useState<LogPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [devices, setDevices] = useState<Device[]>([])
  const [types, setTypes] = useState<string[]>([])
  const [detail, setDetail] = useState<AccessLogDetail | null>(null)

  function update(patch: Partial<typeof f>) {
    const next = { ...f, page: 1, ...patch }
    const out = new URLSearchParams()
    Object.entries(next).forEach(([k, v]) => v !== '' && v !== null && out.set(k, String(v)))
    setParams(out, { replace: true })
  }

  useEffect(() => {
    api<Device[]>('/api/devices').then(setDevices, () => {})
    api<string[]>('/api/logs/types').then(setTypes, () => {})
  }, [])

  // Debounce the free-text search.
  useEffect(() => {
    if (search === f.q) return
    const t = window.setTimeout(() => update({ q: search }), 350)
    return () => window.clearTimeout(t)
  }, [search]) // eslint-disable-line react-hooks/exhaustive-deps

  const query = params.toString()
  useEffect(() => {
    const qs = new URLSearchParams({
      date_from: f.date_from,
      date_to: f.date_to,
      sort: f.sort,
      page: String(f.page),
      page_size: String(f.page_size),
    })
    for (const k of ['device_id', 'q', 'type', 'result'] as const) if (f[k]) qs.set(k, f[k])
    let cancelled = false
    api<LogPage>(`/api/logs?${qs}`).then(
      (d) => !cancelled && (setData(d), setError(null)),
      (e: Error) => !cancelled && setError(e.message),
    )
    return () => {
      cancelled = true
    }
  }, [query]) // eslint-disable-line react-hooks/exhaustive-deps

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <section>
      <div className="page-head">
        <h2>
          Access logs <SourceTag source="device" />
        </h2>
        <span className="muted small">Imported from the devices; read-only. Times in Asia/Beirut.</span>
      </div>

      <div className="card filters">
        <label>
          From
          <input type="date" value={f.date_from} max={f.date_to} onChange={(e) => update({ date_from: e.target.value })} />
        </label>
        <label>
          To
          <input type="date" value={f.date_to} min={f.date_from} onChange={(e) => update({ date_to: e.target.value })} />
        </label>
        <label>
          Device
          <select value={f.device_id} onChange={(e) => update({ device_id: e.target.value })}>
            <option value="">All devices</option>
            {devices.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <label className="grow">
          Search
          <input type="search" value={search} placeholder="Name, card number or user ID" onChange={(e) => setSearch(e.target.value)} />
        </label>
        <label>
          Type
          <select value={f.type} onChange={(e) => update({ type: e.target.value })}>
            <option value="">Any</option>
            {types.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          Result
          <select value={f.result} onChange={(e) => update({ result: e.target.value })}>
            <option value="">Any</option>
            <option value="granted">Granted</option>
            <option value="denied">Denied</option>
          </select>
        </label>
        <div className="quick">
          <button className="secondary" onClick={() => update({ date_from: today, date_to: today })}>
            Today
          </button>
          <button className="secondary" onClick={() => update({ date_from: addDays(today, -6), date_to: today })}>
            7 days
          </button>
          <button className="secondary" onClick={() => update({ date_from: addDays(today, -29), date_to: today })}>
            30 days
          </button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      <div className="card">
        <div className="table-head">
          <span>{data ? `${data.total.toLocaleString()} record(s)` : 'Loading…'}</span>
          <button className="link" onClick={() => update({ sort: f.sort === 'desc' ? 'asc' : 'desc', page: f.page })}>
            {f.sort === 'desc' ? 'Newest first ↓' : 'Oldest first ↑'}
          </button>
        </div>
        <table className="logs">
          <thead>
            <tr>
              <th>Time</th>
              <th>Device</th>
              <th>Name</th>
              <th>User ID</th>
              <th>Card no.</th>
              <th>Type</th>
              <th>Result</th>
              <th>Method</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((l) => (
              <tr key={l.id} className="clickable" onClick={() => api<AccessLogDetail>(`/api/logs/${l.id}`).then(setDetail)}>
                <td className="nowrap">{formatDateTime(l.event_time)}</td>
                <td>{l.device_name}</td>
                <td>{l.card_name ?? '—'}</td>
                <td className="mono">{l.device_user_id ?? '—'}</td>
                <td className="mono">{l.card_no ?? '—'}</td>
                <td>{l.type ?? '—'}</td>
                <td>
                  {l.granted === null ? (
                    '—'
                  ) : (
                    <span className={`badge ${l.granted ? 'status-online' : 'status-offline'}`}>{l.granted ? 'Granted' : 'Denied'}</span>
                  )}
                </td>
                <td>{methodLabel(l.method)}</td>
              </tr>
            ))}
            {data?.items.length === 0 && (
              <tr>
                <td colSpan={8} className="muted">
                  No records match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <div className="pager">
          <button className="secondary" disabled={f.page <= 1} onClick={() => update({ page: f.page - 1 })}>
            ← Previous
          </button>
          <span>
            Page {f.page} of {pages}
          </span>
          <button className="secondary" disabled={f.page >= pages} onClick={() => update({ page: f.page + 1 })}>
            Next →
          </button>
          <select value={f.page_size} onChange={(e) => update({ page_size: Number(e.target.value) })}>
            {PAGE_SIZES.map((n) => (
              <option key={n} value={n}>
                {n} / page
              </option>
            ))}
          </select>
        </div>
      </div>

      {detail && (
        <div className="overlay" onClick={() => setDetail(null)}>
          <div className="card dialog" onClick={(e) => e.stopPropagation()}>
            <div className="page-head">
              <h3>
                Record #{detail.rec_no} · {detail.device_name}
              </h3>
              <button className="link" onClick={() => setDetail(null)}>
                Close
              </button>
            </div>
            <p className="muted small">
              Event {formatDateTime(detail.event_time)} · imported {formatDateTime(detail.imported_at)}. Raw fields as reported by
              the device (PINs are never stored).
            </p>
            <dl className="kv">
              {Object.entries(detail.raw_payload).map(([k, v]) => (
                <div key={k} style={{ display: 'contents' }}>
                  <dt>{k}</dt>
                  <dd className="mono">{v === '' ? <span className="muted">(empty)</span> : v}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      )}
    </section>
  )
}
