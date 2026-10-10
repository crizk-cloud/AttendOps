import type { DeviceStatus } from '../api/types'

const LABEL: Record<DeviceStatus, string> = {
  online: 'Online',
  offline: 'Offline',
  auth_failed: 'Login failed',
  error: 'Error',
  unknown: 'Not checked',
}

export function StatusBadge({ status, checking }: { status: DeviceStatus; checking?: boolean }) {
  return (
    <span className={`badge status-${status}`}>
      {LABEL[status]}
      {checking && <span className="spinner" aria-label="checking" />}
    </span>
  )
}
