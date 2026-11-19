import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ExternalLink, RefreshCw, Sheet } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, errorText } from '../api'
import { useRefreshAll } from '../hooks'
import { timeAgo } from '../lib/format'
import type { SyncInfo } from '../types'
import { useToast } from './ui'

export const useSyncStatus = () =>
  useQuery({ queryKey: ['gsheet-status'], queryFn: () => api.get<SyncInfo & { summary: any }>('/api/gsheet/status'), refetchInterval: 15_000 })

function useTick(ms = 10_000) {
  const [, set] = useState(0)
  useEffect(() => {
    const t = setInterval(() => set((x) => x + 1), ms)
    return () => clearInterval(t)
  }, [ms])
}

/** "Live from Google Sheet · synced 20s ago · Sync now" strip. Renders nothing when live mode is off. */
export function SyncBadge({ compact }: { compact?: boolean }) {
  const { data } = useSyncStatus()
  const refresh = useRefreshAll()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  useTick()
  if (!data?.enabled) return null
  const now = async () => {
    setBusy(true)
    try {
      const r = await api.post<any>('/api/gsheet/sync')
      const d = r.summary?.demos ?? {}, v = r.summary?.revenue ?? {}
      const n = (x: any) => (x.added ?? 0) + (x.updated ?? 0) + (x.deleted ?? 0) + (x.restored ?? 0)
      toast({ tone: 'green', title: 'Synced with Google Sheet', body: n(d) + n(v) ? `Demos +${d.added ?? 0} ~${d.updated ?? 0} −${d.deleted ?? 0} · Revenue +${v.added ?? 0} ~${v.updated ?? 0} −${v.deleted ?? 0}` : 'Already up to date' })
      refresh()
    } catch (e) {
      toast({ tone: 'red', title: 'Sync failed', body: errorText(e) })
    } finally {
      setBusy(false)
    }
  }
  const rejected = (data.summary?.demos?.rejected?.length ?? 0) + (data.summary?.revenue?.rejected?.length ?? 0)
  const alerts = data.summary?.alerts?.length ?? 0
  return (
    <div className={`row wrap ${compact ? '' : 'card tight'}`} style={{ gap: 10, padding: compact ? 0 : '8px 14px', borderColor: data.error ? 'rgba(255,92,108,.45)' : 'rgba(74,222,128,.35)' }}>
      <Sheet size={16} color={data.error ? 'var(--red)' : 'var(--green)'} />
      <span className="small" style={{ fontWeight: 700 }}>{data.error ? 'Google Sheet sync problem' : <><span className="live-dot" /> Live from Google Sheet</>}</span>
      {data.name && <span className="pill" title={data.name} style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{data.name}</span>}
      <span className="small muted">{data.last_success ? `synced ${timeAgo(data.last_success)}` : 'not synced yet'} · every {data.interval}s</span>
      {data.error && <span className="small red" title={data.error}><AlertTriangle size={13} style={{ verticalAlign: -2 }} /> {data.error}</span>}
      {(rejected > 0 || alerts > 0) && <span className="pill amber" title="See Reports & Settings → League settings → Google Sheet">{rejected ? `${rejected} sheet row(s) need fixing` : ''}{rejected && alerts ? ' · ' : ''}{alerts ? `${alerts} alert(s)` : ''}</span>}
      <span className="spacer" />
      {data.url && <a className="btn sm ghost" href={data.url} target="_blank" rel="noreferrer"><ExternalLink size={13} /> Open sheet</a>}
      <button className="btn sm" onClick={now} disabled={busy}><RefreshCw size={13} className={busy ? 'spin' : ''} /> {busy ? 'Syncing…' : 'Sync now'}</button>
    </div>
  )
}

export function LiveLockNotice({ what }: { what: string }) {
  const { data } = useSyncStatus()
  if (!data?.enabled) return null
  return (
    <div className="notice">
      <b>Live Google Sheet mode.</b> {what} come from the Google Sheet — add, edit or remove them there and the app updates within about a minute.
      {data.url && <> <a href={data.url} target="_blank" rel="noreferrer">Open the sheet <ExternalLink size={12} style={{ verticalAlign: -1 }} /></a></>}
    </div>
  )
}

/** Settings card: link, on/off, interval, last result and problem rows. */
export function SheetSettings({ s, set }: { s: any; set: (k: string, v: any) => void }) {
  const { data } = useSyncStatus()
  const sum = data?.summary
  const rows = [...(sum?.demos?.rejected ?? []).map((r: any) => ({ ...r, sheet: 'Demos_and_Pipelines' })),
    ...(sum?.revenue?.rejected ?? []).map((r: any) => ({ ...r, sheet: 'League_Revenue' }))]
  return (
    <div className="card">
      <div className="card-head"><Sheet size={18} /><h3>Live Google Sheet</h3>
        <span className={`pill ${s.gsheet_sync_enabled ? 'green' : 'grey'}`}>{s.gsheet_sync_enabled ? 'On' : 'Off'}</span></div>
      <div className="small muted" style={{ marginBottom: 10 }}>
        When on, the app downloads the sheet on a timer and mirrors <span className="kbd">Demos_and_Pipelines</span> and <span className="kbd">League_Revenue</span>: new rows are added, changed rows updated, removed rows moved to Deleted.
        Rows are matched by <b>Sl No + Customer Name</b>, so changing a Demo Date updates the same demo. The sheet must be shared as <b>“Anyone with the link can view”</b>.
        Demo and revenue editing in the app is locked while this is on (POC remarks/start date and exchange-rate overrides stay editable).
      </div>
      <div className="form-grid">
        <label className="field" style={{ gridColumn: '1 / -1' }}>Google Sheet link<input value={s.gsheet_url ?? ''} onChange={(e) => set('gsheet_url', e.target.value)} /></label>
        <label className="field">Live sync
          <div className="seg"><button type="button" className={s.gsheet_sync_enabled ? 'on' : ''} onClick={() => set('gsheet_sync_enabled', true)}>On</button>
            <button type="button" className={!s.gsheet_sync_enabled ? 'on' : ''} onClick={() => set('gsheet_sync_enabled', false)}>Off</button></div></label>
        <label className="field">Check every (seconds, min 30)<input type="number" min={30} value={s.gsheet_sync_interval_seconds} onChange={(e) => set('gsheet_sync_interval_seconds', Number(e.target.value))} /></label>
      </div>
      <div className="section-label" style={{ marginTop: 16 }}>Sheet format rules (this team)</div>
      <div className="form-grid">
        <label className="field">Which completed demos count
          <div className="seg"><button type="button" className={s.count_requires_qualified ? 'on' : ''} onClick={() => set('count_requires_qualified', true)}>Only Qualified = Yes</button>
            <button type="button" className={!s.count_requires_qualified ? 'on' : ''} onClick={() => set('count_requires_qualified', false)}>Every Completed demo</button></div></label>
        <label className="field">F2F when Demo Type is blank
          <div className="seg"><button type="button" className={s.f2f_from_location ? 'on' : ''} onClick={() => set('f2f_from_location', true)}>From Country / City</button>
            <button type="button" className={!s.f2f_from_location ? 'on' : ''} onClick={() => set('f2f_from_location', false)}>Not counted as F2F</button></div></label>
      </div>
      <div className="tiny dim" style={{ marginTop: 6 }}>
        Required columns: Sl No, BD, Customer Name, Domain, Country <i>or</i> City, Demo On, Demo Date, Status
        {s.count_requires_qualified ? ', Qualified Demo' : ''}{s.f2f_from_location ? '' : ', Demo Type'}. Demo Time and Time Zone are optional.
        “Every Completed demo” still excludes a demo explicitly marked Qualified = No. “From Country / City” treats a demo located in one of this team's F2F countries as F2F.
        A column that is missing from the sheet never overwrites what the app already holds.
      </div>
      {data && (
        <div className="col" style={{ gap: 8, marginTop: 14 }}>
          <div className="small">Sheet: <b>{data.name || '—'}</b>
            {data.last_success && <> · last successful sync: <b>{new Date(data.last_success).toLocaleString()}</b></>}
            {data.last_change && <> · last change from the sheet: <b>{new Date(data.last_change).toLocaleString()}</b></>}</div>
          {data.error && <div className="errors">{data.error}</div>}
          {(sum?.alerts ?? []).map((a: string) => <div key={a} className="notice amber">{a}</div>)}
          {sum && <div className="small muted">Last processed: Demos +{sum.demos?.added ?? 0} / updated {sum.demos?.updated ?? 0} / removed {sum.demos?.deleted ?? 0} / unchanged {sum.demos?.unchanged ?? 0} ·
            Revenue +{sum.revenue?.added ?? 0} / updated {sum.revenue?.updated ?? 0} / removed {sum.revenue?.deleted ?? 0}</div>}
          {rows.length > 0 && (
            <div className="table-wrap"><table className="data">
              <thead><tr><th>Sheet</th><th>Row</th><th>Record</th><th>Fix needed in the sheet</th></tr></thead>
              <tbody>{rows.map((r: any) => <tr key={r.sheet + r.row}><td className="small">{r.sheet}</td><td>{r.row}</td><td>{r.label}</td><td className="small red">{r.errors.join(' · ')}</td></tr>)}</tbody>
            </table></div>)}
        </div>
      )}
    </div>
  )
}
