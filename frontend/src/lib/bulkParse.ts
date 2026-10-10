// Parses the bulk-add text box. One device per line:
//   ip[:port] [, name] [, username, password]
// Blank lines and lines starting with # are ignored. Anything after the 3rd comma belongs to the
// password, so passwords may contain commas.

export interface BulkLine {
  line: number
  ip: string
  port: number
  name?: string
  username?: string
  password?: string
  error?: string
}

const IPV4 = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/

export function parseBulk(text: string): BulkLine[] {
  const out: BulkLine[] = []
  text.split(/\r?\n/).forEach((raw, i) => {
    const line = raw.trim()
    if (!line || line.startsWith('#')) return
    const parts = line.split(',')
    const [addr, name, username, ...rest] = parts.map((p) => p.trim())
    const password = rest.length ? parts.slice(3).join(',').trim() : undefined
    const [ip, portText] = addr.split(':')
    const port = portText ? Number(portText) : 80
    const entry: BulkLine = { line: i + 1, ip, port, name: name || undefined, username: username || undefined, password: password || undefined }
    if (!IPV4.test(ip)) entry.error = 'invalid IP address'
    else if (!Number.isInteger(port) || port < 1 || port > 65535) entry.error = 'invalid port'
    else if (username && !password) entry.error = 'username given without password'
    out.push(entry)
  })
  return out
}
