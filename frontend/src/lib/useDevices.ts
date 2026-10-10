import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Device } from '../api/types'

// Loads the device list; polls quickly while checks are running, slowly otherwise.
export function useDevices() {
  const [devices, setDevices] = useState<Device[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined
    async function tick() {
      try {
        const list = await api<Device[]>('/api/devices')
        if (cancelled) return
        setDevices(list)
        setError(null)
        timer = window.setTimeout(tick, list.some((d) => d.checking || d.syncing) ? 2000 : 30000)
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : 'Failed to load devices')
        timer = window.setTimeout(tick, 30000)
      }
    }
    void tick()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return { devices, error, reload }
}
