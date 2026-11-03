import { CheckCircle2, Pencil, Plus, RotateCcw, Search, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api, errorText } from '../api'
import { DemoForm } from '../components/forms'
import { LiveLockNotice, SyncBadge } from '../components/sync'
import { Empty, Loading, MultiSelect, StatusPill, Tabs, TypePill, useConfirm, useToast } from '../components/ui'
import { useDemos, useMeta, useRefreshAll } from '../hooks'
import { fmtDate, fmtDateTime } from '../lib/format'
import type { Demo } from '../types'

function useNow(ms = 30000) {
  const [n, setN] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => setN(Date.now()), ms)
    return () => clearInterval(t)
  }, [ms])
  return n
}

export function remaining(d: Demo, now: number) {
  if (!d.demo_at) return ''
  const s = Math.floor((new Date(d.demo_at).getTime() - now) / 1000)
  if (s <= 0) return '0 Hrs 0 Min'
  return `${Math.floor(s / 3600)} Hrs ${Math.floor((s % 3600) / 60)} Min`
}

export default function DemoTracker() {
  const [tab, setTab] = useState<'demos' | 'poc' | 'trash'>('demos')
  return (
    <>
      <div className="page-head">
        <div><h1>Demo Tracker</h1><div className="sub">Demos_and_Pipelines · a demo counts only when Status = Completed and Qualified = Yes</div></div>
      </div>
      <div style={{ marginBottom: 12 }}><SyncBadge /></div>
      <Tabs value={tab} onChange={setTab} tabs={[{ key: 'demos', label: 'Demos & pipeline' }, { key: 'poc', label: 'POC tracker' }, { key: 'trash', label: 'Deleted' }]} />
      {tab === 'demos' && <DemoTable />}
      {tab === 'poc' && <PocTable />}
      {tab === 'trash' && <Trash />}
    </>
  )
}

function DemoTable() {
  const { data, isLoading } = useDemos()
  const { data: meta } = useMeta()
  const refresh = useRefreshAll()
  const toast = useToast()
  const confirm = useConfirm()
  const now = useNow()
  const [edit, setEdit] = useState<Demo | null | undefined>(undefined)
  const [q, setQ] = useState('')
  const [bds, setBds] = useState<string[]>([])
  const [sts, setSts] = useState<string[]>([])
  const [types, setTypes] = useState<string[]>([])
  const [view, setView] = useState<'all' | 'upcoming' | 'counted' | 'needs'>('all')
  const live = !!meta?.live_mode

  const rows = useMemo(() => (data ?? []).filter((d) => {
    if (q && !`${d.customer_name} ${d.country ?? ''} ${d.domain ?? ''}`.toLowerCase().includes(q.toLowerCase())) return false
    if (bds.length && !bds.includes(String(d.bd_id))) return false
    if (sts.length && !sts.includes(d.status)) return false
    if (types.length && !types.includes(d.demo_type ?? '(blank)')) return false
    if (view === 'upcoming' && !(d.status === 'Scheduled')) return false
    if (view === 'counted' && !d.counts) return false
    if (view === 'needs' && !((d.status === 'Completed' && !d.qualified) || (d.status === 'Completed' && !d.demo_date) || !d.demo_type)) return false
    return true
  }).sort((a, b) => view === 'upcoming' ? (a.demo_at ?? '').localeCompare(b.demo_at ?? '') : (b.demo_date ?? '').localeCompare(a.demo_date ?? '') || (b.sl_no ?? 0) - (a.sl_no ?? 0)), [data, q, bds, sts, types, view])

  const patch = async (d: Demo, change: Partial<Demo>) => {
    try {
      await api.put(`/api/demos/${d.id}`, { ...d, ...change })
      refresh()
    } catch (e) { toast({ tone: 'red', title: `Not saved — ${d.customer_name}`, body: errorText(e) }) }
  }
  const markQualified = (d: Demo) => patch(d, { status: 'Completed', qualified: 'Yes' })
  const del = async (d: Demo) => {
    if (!(await confirm({ title: 'Delete demo?', danger: true, confirm: 'Move to Deleted', body: <>“{d.customer_name}” ({d.bd_name}) will be removed from all counts. You can restore it from the Deleted tab.</> }))) return
    await api.del(`/api/demos/${d.id}`)
    refresh()
  }

  if (isLoading) return <Loading />
  const needs = (data ?? []).filter((d) => (d.status === 'Completed' && !d.qualified) || !d.demo_type).length
  return (
    <div className="col" style={{ gap: 12 }}>
      <LiveLockNotice what="Demos" />
      <div className="row wrap">
        <div style={{ position: 'relative', flex: '1 1 220px', maxWidth: 320 }}>
          <Search size={15} style={{ position: 'absolute', left: 10, top: 11, color: 'var(--dim)' }} />
          <input placeholder="Search customer, country, domain" value={q} onChange={(e) => setQ(e.target.value)} style={{ paddingLeft: 32 }} />
        </div>
        <div style={{ width: 170 }}><MultiSelect placeholder="All BDs" value={bds} onChange={setBds} options={(meta?.bds ?? []).map((b) => ({ value: String(b.id), label: b.name }))} /></div>
        <div style={{ width: 170 }}><MultiSelect placeholder="All statuses" value={sts} onChange={setSts} options={(meta?.demo_statuses ?? []).map((s) => ({ value: s, label: s }))} /></div>
        <div style={{ width: 140 }}><MultiSelect placeholder="All types" value={types} onChange={setTypes} options={['F2F', 'Virtual', '(blank)'].map((s) => ({ value: s, label: s }))} /></div>
        <div className="seg">
          {([['all', 'All'], ['upcoming', 'Upcoming'], ['counted', 'Counted'], ['needs', `Needs attention${needs ? ` (${needs})` : ''}`]] as const).map(([k, l]) =>
            <button key={k} className={view === k ? 'on' : ''} onClick={() => setView(k)}>{l}</button>)}
        </div>
        <span className="spacer" />
        <span className="small muted">{rows.length} of {data?.length ?? 0}</span>
        {!live && <button className="btn primary" onClick={() => setEdit(null)}><Plus size={16} /> Add demo</button>}
      </div>
      {rows.length === 0 ? <Empty>No demos match.</Empty> : (
        <div className="table-wrap">
          <table className="data">
            <thead><tr>
              <th>Sl</th><th>BD</th><th>Customer</th><th>Domain</th><th>Country</th><th>Demo Type</th><th>Demo On</th><th>Date</th><th>Time</th>
              <th>TZ</th><th>Time remaining</th><th>Status</th><th>Qualified</th><th>League</th><th></th>
            </tr></thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id}>
                  <td className="dim">{d.sl_no ?? ''}</td>
                  <td className="nowrap" style={{ fontWeight: 600 }}>{d.bd_name}</td>
                  <td style={{ fontWeight: 600 }}>{d.customer_name}</td>
                  <td className="small">{d.domain ?? <span className="dim">—</span>}</td>
                  <td className="small">{d.country ?? <span className="dim">—</span>}{d.region && <div className="tiny gold">{d.region}</div>}</td>
                  <td>
                    <select value={d.demo_type ?? ''} disabled={live} onChange={(e) => patch(d, { demo_type: (e.target.value || null) as any })} style={{ minHeight: 30, padding: '3px 6px', width: 92 }} aria-label="Demo Type">
                      <option value="">—</option><option>F2F</option><option>Virtual</option>
                    </select>
                  </td>
                  <td className="small">{d.demo_on}</td>
                  <td className="nowrap">{fmtDate(d.demo_date)}</td>
                  <td className="nowrap">{d.demo_time ?? ''}</td>
                  <td className="small">{d.time_zone ?? ''}</td>
                  <td className="nowrap small">{d.status === 'Scheduled' ? <span className={d.demo_at && new Date(d.demo_at).getTime() - now < 3 * 3600e3 ? 'amber' : ''}>{remaining(d, now)}</span> : <span className="dim">{d.demo_at ? remaining(d, now) : ''}</span>}</td>
                  <td>
                    <select value={d.status} disabled={live} onChange={(e) => patch(d, { status: e.target.value, qualified: e.target.value === 'Completed' || meta?.poc_statuses.includes(e.target.value) ? d.qualified : d.qualified === 'Yes' ? null : d.qualified })}
                      style={{ minHeight: 30, padding: '3px 6px', width: 150 }} aria-label="Status">
                      {meta?.demo_statuses.map((s) => <option key={s}>{s}</option>)}
                    </select>
                  </td>
                  <td>
                    <select value={d.qualified ?? ''} disabled={live} onChange={(e) => patch(d, { qualified: (e.target.value || null) as any })} style={{ minHeight: 30, padding: '3px 6px', width: 70 }} aria-label="Qualified">
                      <option value="">—</option><option disabled={!(d.status === 'Completed' || meta?.poc_statuses.includes(d.status))}>Yes</option><option>No</option>
                    </select>
                  </td>
                  <td>{d.counts ? <span className="pill green" title="Counts toward official league totals"><CheckCircle2 size={12} /> Counts</span>
                    : d.status === 'Completed' && !d.qualified ? <span className="pill amber">Qualify?</span>
                      : d.demo_date && !d.in_league ? <span className="pill grey">Pre-league</span> : null}
                    {d.counts_f2f && <span className="pill gold" style={{ marginLeft: 4 }}>F2F 45</span>}</td>
                  <td className="nowrap">
                    {!live && d.status === 'Scheduled' && d.demo_date && d.demo_at && new Date(d.demo_at).getTime() < now &&
                      <button className="btn sm" title="Mark Completed + Qualified" onClick={() => markQualified(d)}><CheckCircle2 size={14} /></button>}
                    <button className="btn sm ghost" onClick={() => setEdit(d)} aria-label={live ? 'View' : 'Edit'}><Pencil size={14} /></button>
                    {!live && <button className="btn sm ghost" onClick={() => del(d)} aria-label="Delete"><Trash2 size={14} /></button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {edit !== undefined && <DemoForm demo={edit} onClose={() => setEdit(undefined)} />}
    </div>
  )
}

function PocTable() {
  const { data, isLoading } = useDemos()
  const { data: meta } = useMeta()
  const refresh = useRefreshAll()
  const toast = useToast()
  const [edit, setEdit] = useState<Demo | null | undefined>(undefined)
  if (isLoading) return <Loading />
  const rows = (data ?? []).filter((d) => meta?.poc_statuses.includes(d.status))
  const counts = Object.fromEntries((meta?.poc_statuses ?? []).map((s) => [s, rows.filter((r) => r.status === s).length]))
  const setStatus = async (d: Demo, status: string) => {
    try { await api.put(`/api/demos/${d.id}`, { ...d, status }); refresh() } catch (e) { toast({ tone: 'red', title: 'Not saved', body: errorText(e) }) }
  }
  return (
    <div className="col" style={{ gap: 12 }}>
      <div className="kpis">{(meta?.poc_statuses ?? []).map((s) => (
        <div key={s} className="kpi" style={{ ['--accent' as any]: s === 'POC Completed' ? 'var(--gold)' : s === 'POC Paused' ? 'var(--amber)' : 'var(--violet)' }}>
          <div className="label">{s}</div><div className="value">{counts[s]}</div></div>))}
      </div>
      <div className="notice">POC status comes from the demo's Status column. Moving a demo into POC never adds a demo and never removes an already-achieved qualified demo.</div>
      {rows.length === 0 ? <Empty>No POCs yet. Set a demo's Status to “POC Initiated” to start tracking it here.</Empty> : (
        <div className="table-wrap"><table className="data">
          <thead><tr><th>Customer</th><th>BD</th><th>Related demo</th><th>POC status</th><th>POC start</th><th>Last updated</th><th>Remarks</th><th>Demo counted</th><th></th></tr></thead>
          <tbody>{rows.map((d) => (
            <tr key={d.id}>
              <td style={{ fontWeight: 600 }}>{d.customer_name}</td><td>{d.bd_name}</td>
              <td className="small">{d.demo_on ?? 'Demo'} · {fmtDate(d.demo_date)} <TypePill type={d.demo_type} /></td>
              <td><select value={d.status} disabled={meta?.live_mode} onChange={(e) => setStatus(d, e.target.value)} style={{ minHeight: 30, padding: '3px 6px', width: 150 }}>
                {meta?.poc_statuses.map((s) => <option key={s}>{s}</option>)}</select></td>
              <td>{fmtDate(d.poc_started_on)}</td><td className="small">{fmtDateTime(d.poc_status_updated_at ?? d.updated_at)}</td>
              <td className="small" style={{ maxWidth: 280 }}>{d.poc_remarks ?? <span className="dim">—</span>}</td>
              <td>{d.counts ? <span className="pill green">Yes</span> : <span className="pill grey">No</span>}</td>
              <td><button className="btn sm ghost" onClick={() => setEdit(d)}><Pencil size={14} /></button></td>
            </tr>))}</tbody>
        </table></div>
      )}
      {edit !== undefined && <DemoForm demo={edit} onClose={() => setEdit(undefined)} />}
    </div>
  )
}

function Trash() {
  const { data, isLoading } = useDemos(true)
  const { data: meta } = useMeta()
  const refresh = useRefreshAll()
  if (isLoading) return <Loading />
  if (!data?.length) return <Empty>No deleted demos.</Empty>
  return (
    <div className="table-wrap"><table className="data">
      <thead><tr><th>Customer</th><th>BD</th><th>Status</th><th>Date</th><th>Deleted</th><th></th></tr></thead>
      <tbody>{data.map((d) => (
        <tr key={d.id}><td>{d.customer_name}</td><td>{d.bd_name}</td><td><StatusPill status={d.status} /></td><td>{fmtDate(d.demo_date)}</td>
          <td className="small">{fmtDateTime(d.deleted_at)}</td>
          <td>{meta?.live_mode ? <span className="tiny dim">Add the row back in the sheet to restore</span> : <button className="btn sm" onClick={async () => { await api.post(`/api/demos/${d.id}/restore`); refresh() }}><RotateCcw size={14} /> Restore</button>}</td></tr>))}
      </tbody></table></div>
  )
}
