export class ApiError extends Error {
  status: number
  detail: any
  constructor(status: number, detail: any) {
    super(typeof detail === 'string' ? detail : detail?.message || (detail?.errors || []).join('; ') || `Error ${status}`)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(method: string, url: string, body?: unknown, isForm = false): Promise<T> {
  const headers: Record<string, string> = { 'X-Requested-With': 'ffl' }
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json'
  const res = await fetch(url, {
    method,
    headers,
    credentials: 'same-origin',
    body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
  })
  if (res.status === 401 && !url.includes('/auth/') && !url.includes('/arena')) {
    window.dispatchEvent(new Event('ffl:unauthorized'))
  }
  if (!res.ok) {
    let detail: any = res.statusText
    try {
      detail = (await res.json()).detail
    } catch { /* not json */ }
    throw new ApiError(res.status, detail)
  }
  const ct = res.headers.get('content-type') || ''
  return (ct.includes('application/json') ? res.json() : (res.blob() as unknown)) as Promise<T>
}

export const api = {
  get: <T,>(url: string) => request<T>('GET', url),
  post: <T,>(url: string, body?: unknown) => request<T>('POST', url, body ?? {}),
  put: <T,>(url: string, body: unknown) => request<T>('PUT', url, body),
  del: <T,>(url: string) => request<T>('DELETE', url),
  upload: <T,>(url: string, form: FormData) => request<T>('POST', url, form, true),
}

/** Download an xlsx from GET or POST endpoints. */
export async function download(url: string, body?: unknown) {
  const res = await fetch(url, {
    method: body ? 'POST' : 'GET',
    headers: { 'X-Requested-With': 'ffl', ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
  })
  if (!res.ok) throw new ApiError(res.status, res.statusText)
  const cd = res.headers.get('content-disposition') || ''
  const name = /filename="([^"]+)"/.exec(cd)?.[1] || 'export.xlsx'
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail
    if (d?.errors) return d.errors.join(' · ')
    if (typeof d === 'string') return d
    if (d?.message) return d.message
    if (Array.isArray(d)) return d.map((x: any) => `${(x.loc || []).slice(1).join('.')}: ${x.msg}`).join(' · ')
    return e.message
  }
  return e instanceof Error ? e.message : String(e)
}
