import type { SyncStatus } from '../api/types'

const CLS: Record<SyncStatus, string> = {
  success: 'status-online',
  partial: 'status-auth_failed',
  failed: 'status-offline',
  running: 'status-unknown',
}

export function SyncBadge({ status, syncing }: { status: SyncStatus | null; syncing?: boolean }) {
  if (syncing) {
    return (
      <span className="badge status-unknown">
        Syncing <span className="spinner" />
      </span>
    )
  }
  if (!status) return <span className="muted small">never synced</span>
  return <span className={`badge ${CLS[status]}`}>{status}</span>
}
