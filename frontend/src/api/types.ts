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
