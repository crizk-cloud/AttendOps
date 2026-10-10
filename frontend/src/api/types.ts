export type Role = 'viewer' | 'operator' | 'admin'

export const ROLE_RANK: Record<Role, number> = { viewer: 0, operator: 1, admin: 2 }

export interface AppUser {
  id: number
  email: string
  full_name: string | null
  role: Role
  is_active: boolean
  created_at: string
  last_login_at: string | null
}

export type DeviceStatus = 'unknown' | 'online' | 'offline' | 'auth_failed' | 'error'
export type CapabilityState = 'verified' | 'unsupported' | 'unverified'

export interface Device {
  id: number
  // configured in AttendOps
  name: string
  vendor: string
  ip: string
  port: number
  username: string | null // admins only
  enabled: boolean
  notes: string | null
  // reported by the device
  model: string | null
  firmware: string | null
  serial_no: string | null
  capabilities: Record<string, { state: CapabilityState; detail: string }> | null
  capabilities_checked_at: string | null
  // observed by AttendOps
  status: DeviceStatus
  last_seen_at: string | null
  last_checked_at: string | null
  last_error: string | null
  last_response_ms: number | null
  checking: boolean
  // history sync
  synced_until: string | null
  last_sync_at: string | null
  last_sync_status: SyncStatus | null
  syncing: boolean
  created_at: string
}

export interface ConnectionTestResult {
  status: DeviceStatus
  model: string | null
  firmware: string | null
  serial_no: string | null
  error: string | null
  response_ms: number | null
}

export type SyncStatus = 'running' | 'success' | 'partial' | 'failed'

export interface AccessLog {
  id: number
  device_id: number
  device_name: string
  rec_no: number
  event_time: string | null
  device_user_id: string | null
  card_name: string | null
  card_no: string | null
  type: string | null
  method: number | null
  status: number | null
  door: number | null
  reader_id: string | null
  error_code: number | null
  granted: boolean | null
}

export interface AccessLogDetail extends AccessLog {
  raw_payload: Record<string, string>
  imported_at: string
}

export interface LogPage {
  items: AccessLog[]
  total: number
  page: number
  page_size: number
}

export interface SyncRun {
  id: number
  device_id: number
  device_name: string | null
  trigger: string
  started_at: string
  finished_at: string | null
  status: SyncStatus
  window_start: string
  window_end: string
  synced_until: string | null
  records_found: number
  records_inserted: number
  records_existing: number
  queries: number
  warnings: unknown[] | null
  error_message: string | null
}
