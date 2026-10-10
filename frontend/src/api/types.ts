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
