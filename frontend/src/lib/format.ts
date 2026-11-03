const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

/** ₹ with Indian grouping, e.g. ₹12,50,000 */
export const fmtINR = (v: number | null | undefined) => (v == null ? '—' : `₹${inr.format(Math.round(v))}`)

/** Compact lakh/crore, e.g. ₹12.5 L, ₹1.2 Cr */
export function fmtLakh(v: number | null | undefined): string {
  if (v == null) return '—'
  if (Math.abs(v) >= 1e7) return `₹${(v / 1e7).toFixed(2).replace(/\.?0+$/, '')} Cr`
  if (Math.abs(v) >= 1e5) return `₹${(v / 1e5).toFixed(2).replace(/\.?0+$/, '')} L`
  return fmtINR(v)
}

export const fmtMoney = (cur: string, v: number) =>
  `${cur} ${new Intl.NumberFormat(cur === 'INR' ? 'en-IN' : 'en-US', { maximumFractionDigits: 2 }).format(v)}`

export function fmtDate(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short', year: 'numeric' }) {
  if (!iso) return '—'
  const d = iso.length === 10 ? new Date(iso + 'T00:00:00') : new Date(iso)
  return d.toLocaleDateString('en-GB', opts)
}

export const fmtDay = (iso: string) => fmtDate(iso, { weekday: 'short', day: '2-digit', month: 'short' })

export function fmtDateTime(iso: string | null | undefined) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export function timeAgo(iso: string) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

export const ordinal = (n: number) => {
  const s = ['th', 'st', 'nd', 'rd'], v = n % 100
  return n + (s[(v - 20) % 10] || s[v] || s[0])
}

export const initials = (name: string) => name.split(/\s+/).map((p) => p[0]).join('').slice(0, 2).toUpperCase()

/** "A, B & C" — commas between names, & only before the last. */
export function joinNames(names: string[]): string {
  if (!names.length) return ''
  if (names.length === 1) return names[0]
  if (names.length === 2) return `${names[0]} & ${names[1]}`
  return `${names.slice(0, -1).join(', ')} & ${names[names.length - 1]}`
}

/** Stable per-BD accent hue for avatars. */
export function bdHue(id: number) {
  const hues = [205, 160, 280, 330, 25, 50, 190, 120, 255]
  return hues[id % hues.length]
}
