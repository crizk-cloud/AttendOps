import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, refreshAccessToken, setAccessToken, setSessionLostHandler } from '../api/client'
import { ROLE_RANK, type AppUser, type Role } from '../api/types'
import { AuthContext } from './useAuth'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AppUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setSessionLostHandler(() => setUser(null))
    // Restore the session from the refresh cookie on page load.
    refreshAccessToken()
      .then(async (ok) => (ok ? setUser(await api<AppUser>('/api/auth/me')) : null))
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await api<{ access_token: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
    setAccessToken(tokens.access_token)
    setUser(await api<AppUser>('/api/auth/me'))
  }, [])

  const logout = useCallback(async () => {
    try {
      await api('/api/auth/logout', { method: 'POST' })
    } finally {
      setAccessToken(null)
      setUser(null)
    }
  }, [])

  const hasRole = useCallback((min: Role) => !!user && ROLE_RANK[user.role] >= ROLE_RANK[min], [user])

  const value = useMemo(() => ({ user, loading, login, logout, hasRole }), [user, loading, login, logout, hasRole])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
