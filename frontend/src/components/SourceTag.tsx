// Marks where a value comes from, so device-reported data is never confused with app data.
export function SourceTag({ source }: { source: 'device' | 'app' | 'observed' }) {
  const text = { device: 'Reported by device', app: 'Set in AttendOps', observed: 'Observed by AttendOps' }[source]
  return <span className={`source source-${source}`}>{text}</span>
}
