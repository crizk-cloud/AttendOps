// All times are shown in the app's zone (Asia/Beirut), regardless of the viewer's browser zone.
export const APP_TIME_ZONE = 'Asia/Beirut'

const fmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: APP_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return fmt.format(new Date(iso))
}
