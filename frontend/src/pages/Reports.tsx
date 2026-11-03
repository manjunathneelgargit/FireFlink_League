import { useQuery } from '@tanstack/react-query'
import { Download, FileSpreadsheet, Filter, Plus, RefreshCw, Save, Upload, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, download, errorText } from '../api'
import { DailyBars } from '../components/charts'
import { SheetSettings, useSyncStatus } from '../components/sync'
import { Empty, Loading, MultiSelect, StatusPill, Tabs, TypePill, useConfirm, useToast } from '../components/ui'
import { useMeta, useRefreshAll, useSnapshot } from '../hooks'
import { fmtDate, fmtDateTime, fmtINR, fmtLakh } from '../lib/format'
import { setReducedMotion, useReducedMotion } from '../lib/prefs'
import type { Demo, Revenue } from '../types'

type Tab = 'reports' | 'import' | 'export' | 'settings' | 'bds' | 'audit'

export default function Reports() {
  const [tab, setTab] = useState<Tab>('reports')
  return (
    <>
      <div className="page-head"><div><h1>Reports & Settings</h1><div className="sub">Analytical reports, Excel import/export, league configuration and audit history</div></div></div>
      <Tabs value={tab} onChange={setTab} tabs={[
        { key: 'reports', label: 'Filtered reports' }, { key: 'import', label: 'Import workbook' }, { key: 'export', label: 'Export' },
        { key: 'settings', label: 'League settings' }, { key: 'bds', label: 'BD members' }, { key: 'audit', label: 'Audit log' }]} />
      {tab === 'reports' && <FilteredReports />}
      {tab === 'import' && <ImportWizard />}
      {tab === 'export' && <Exports />}
      {tab === 'settings' && <SettingsForm />}
      {tab === 'bds' && <BDMembers />}
      {tab === 'audit' && <AuditLog />}
    </>
  )
}

/* ================================================================== filtered reports */
interface Filters {
  from_date: string; to_date: string; bd_ids: string[]; customer: string; countries: string[]; domains: string[]
  demo_types: string[]; statuses: string[]; qualified: string[]; contract_statuses: string[]; currencies: string[]
}
const EMPTY_F: Filters = { from_date: '', to_date: '', bd_ids: [], customer: '', countries: [], domains: [], demo_types: [], statuses: [], qualified: [], contract_statuses: [], currencies: [] }
const toBody = (f: Filters) => ({ ...f, from_date: f.from_date || null, to_date: f.to_date || null, bd_ids: f.bd_ids.map(Number), customer: f.customer || null })

function FilteredReports() {
  const { data: meta } = useMeta()
  const { data: snap } = useSnapshot()
  const toast = useToast()
  const [draft, setDraft] = useState<Filters>(EMPTY_F)
  const [applied, setApplied] = useState<Filters>(EMPTY_F)
  const res = useQuery({ queryKey: ['report', applied], queryFn: () => api.post<any>('/api/reports/query', toBody(applied)) })
  const set = (k: keyof Filters, v: any) => setDraft((d) => ({ ...d, [k]: v }))
  const opts = (xs: string[] = []) => xs.map((x) => ({ value: x, label: x }))
  const active = Object.entries(applied).filter(([, v]) => (Array.isArray(v) ? v.length : v)).length
  const r = res.data
  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="card">
        <div className="card-head"><Filter size={16} /><h3>Filters</h3><span className="hint">Combine any filters. Dates are inclusive (demo date for demos; signed/credited date for revenue).</span></div>
        <div className="form-grid">
          <label className="field">From date<input type="date" value={draft.from_date} onChange={(e) => set('from_date', e.target.value)} /></label>
          <label className="field">To date<input type="date" value={draft.to_date} onChange={(e) => set('to_date', e.target.value)} /></label>
          <label className="field">BD<MultiSelect placeholder="All BDs" value={draft.bd_ids} onChange={(v) => set('bd_ids', v)} options={(meta?.bds ?? []).map((b) => ({ value: String(b.id), label: b.name }))} /></label>
          <label className="field">Customer name<input value={draft.customer} onChange={(e) => set('customer', e.target.value)} placeholder="contains…" /></label>
          <label className="field">Country<MultiSelect placeholder="All" value={draft.countries} onChange={(v) => set('countries', v)} options={opts(meta?.countries)} /></label>
          <label className="field">Domain<MultiSelect placeholder="All" value={draft.domains} onChange={(v) => set('domains', v)} options={opts(meta?.domains)} /></label>
          <label className="field">Demo Type<MultiSelect placeholder="All" value={draft.demo_types} onChange={(v) => set('demo_types', v)} options={opts(['F2F', 'Virtual', '(blank)'])} /></label>
          <label className="field">Demo Status<MultiSelect placeholder="All" value={draft.statuses} onChange={(v) => set('statuses', v)} options={opts(meta?.demo_statuses)} /></label>
          <label className="field">Qualified Demo<MultiSelect placeholder="All" value={draft.qualified} onChange={(v) => set('qualified', v)} options={opts(['Yes', 'No', '(blank)'])} /></label>
          <label className="field">Revenue Contract Status<MultiSelect placeholder="All" value={draft.contract_statuses} onChange={(v) => set('contract_statuses', v)} options={opts(meta?.contract_statuses)} /></label>
          <label className="field">Currency<MultiSelect placeholder="All" value={draft.currencies} onChange={(v) => set('currencies', v)} options={opts(meta?.currencies)} /></label>
        </div>
        <div className="row wrap" style={{ marginTop: 14 }}>
          <button className="btn primary" onClick={() => setApplied(draft)}><Filter size={14} /> Apply filters</button>
          <button className="btn" onClick={() => { setDraft(EMPTY_F); setApplied(EMPTY_F) }}><X size={14} /> Clear filters</button>
          <span className="spacer" />
          {r && <span className="pill blue">{r.matching.total} matching records · {r.matching.demos} demos · {r.matching.revenue} revenue</span>}
          <button className="btn" onClick={() => download('/api/export/filtered', toBody(applied)).catch((e) => toast({ tone: 'red', title: 'Export failed', body: errorText(e) }))}><Download size={14} /> Export filtered results</button>
        </div>
        <div className="tiny dim" style={{ marginTop: 8 }}>Demo Type / Status / Qualified filters apply to demos only; Contract Status / Currency apply to revenue only.</div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(380px, 100%), 1fr))' }}>
        <div className="card" style={{ borderColor: 'rgba(143,132,255,.45)' }}>
          <div className="row"><span className="pill blue">Filtered Results</span><span className="small muted">{active ? `${active} filter(s) applied` : 'No filters — all records'}</span></div>
          <div className="small muted" style={{ marginTop: 6 }}>Analytical view only. It never changes the official league standings or awards.</div>
        </div>
        <div className="card gold-edge">
          <div className="row"><span className="tag-final">Official League Standings</span><span className="small muted">complete league data, unaffected by filters</span></div>
          <div className="small" style={{ marginTop: 6 }}>Leader: <b className="gold">{snap?.overall.filter((x) => x.is_leader).map((x) => x.bd_name).join(' & ') || '—'}</b> · {snap?.kpis.qualified_completed ?? 0} qualified demos · F2F {snap?.f2f.achieved ?? 0}/{snap?.f2f.target ?? 45} · revenue {fmtLakh(snap?.kpis.total_revenue_inr ?? 0)}</div>
        </div>
      </div>

      {!r ? <Loading /> : (
        <>
          <div className="kpis">
            {[['Qualified completed', r.kpis.qualified_completed, 'var(--gold)'], ['Qualified F2F', r.kpis.qualified_f2f, 'var(--fire)'], ['Qualified Virtual', r.kpis.qualified_virtual, 'var(--blue)'],
              ['Scheduled', r.kpis.scheduled, 'var(--blue)'], ['Completed, not qualified', r.kpis.completed_unqualified, 'var(--amber)']].map(([l, v, c]) => (
              <div className="kpi" key={l as string} style={{ ['--accent' as any]: c }}><div className="label">{l}</div><div className="value">{v}</div></div>))}
            <div className="kpi" style={{ ['--accent' as any]: 'var(--green)' }}><div className="label">Eligible revenue</div><div className="value">{fmtLakh(r.kpis.revenue_inr)}</div>
              {r.kpis.pending_conversion > 0 && <div className="foot amber">{r.kpis.pending_conversion} pending conversion</div>}</div>
          </div>
          <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(420px, 100%), 1fr))' }}>
            <div className="card"><div className="card-head"><h3>By BD</h3><span className="pill blue">Filtered</span></div>
              <div className="table-wrap"><table className="data">
                <thead><tr><th>BD</th><th className="num">Qualified</th><th className="num">F2F</th><th className="num">Virtual</th><th className="num">Scheduled</th><th className="num">Compl. unqual.</th><th className="num">Revenue</th></tr></thead>
                <tbody>{r.by_bd.map((b: any) => <tr key={b.bd_id}><td>{b.bd_name}</td><td className="num">{b.qualified}</td><td className="num">{b.f2f}</td><td className="num">{b.virtual}</td><td className="num">{b.scheduled}</td><td className="num">{b.completed_unqualified}</td><td className="num">{fmtLakh(b.revenue_inr)}</td></tr>)}</tbody>
              </table></div></div>
            <div className="card"><div className="card-head"><h3>Qualified demos by date</h3><span className="pill blue">Filtered</span></div>
              <DailyBars data={Object.entries(r.by_date).map(([date, value]) => ({ date, value: value as number }))} />
              <div className="row wrap small" style={{ gap: 6, marginTop: 8 }}>{Object.entries(r.by_status).map(([k, v]) => <span key={k} className="pill grey">{k}: {v as number}</span>)}</div>
            </div>
          </div>
          <div className="card"><div className="card-head"><h3>Matching demos</h3><span className="hint">{r.demos.length}</span></div>
            {!r.demos.length ? <Empty>No demos match.</Empty> : <div className="table-wrap" style={{ maxHeight: 420 }}><table className="data">
              <thead><tr><th>Date</th><th>BD</th><th>Customer</th><th>Domain</th><th>Country</th><th>Type</th><th>Status</th><th>Qualified</th><th>Counts</th></tr></thead>
              <tbody>{r.demos.map((d: Demo) => <tr key={d.id}><td className="nowrap">{fmtDate(d.demo_date)}</td><td>{d.bd_name}</td><td>{d.customer_name}</td><td className="small">{d.domain}</td><td className="small">{d.country}</td>
                <td><TypePill type={d.demo_type} /></td><td><StatusPill status={d.status} /></td><td>{d.qualified ?? '—'}</td><td>{d.counts ? <span className="pill green">Yes</span> : ''}</td></tr>)}</tbody></table></div>}
          </div>
          <div className="card"><div className="card-head"><h3>Matching revenue</h3><span className="hint">{r.revenue.length}</span></div>
            {!r.revenue.length ? <Empty>No revenue records match.</Empty> : <div className="table-wrap"><table className="data">
              <thead><tr><th>BD</th><th>Customer</th><th>Opportunity</th><th>Status</th><th>Currency</th><th className="num">Value</th><th className="num">INR</th><th>Eligibility</th></tr></thead>
              <tbody>{r.revenue.map((x: Revenue) => <tr key={x.id}><td>{x.bd_name}</td><td>{x.customer_name}</td><td>{x.opportunity_name}</td><td>{x.contract_status}</td><td>{x.currency}</td>
                <td className="num">{x.contract_value.toLocaleString()}</td><td className="num">{x.evaluation.inr_value != null ? fmtINR(x.evaluation.inr_value) : '—'}</td><td className="small">{x.evaluation.eligible ? 'Counted' : x.evaluation.reason}</td></tr>)}</tbody></table></div>}
          </div>
        </>
      )}
    </div>
  )
}

/* ================================================================== import */
function ImportWizard() {
  const toast = useToast()
  const confirm = useConfirm()
  const refresh = useRefreshAll()
  const history = useQuery({ queryKey: ['import-history'], queryFn: () => api.get<any[]>('/api/import/history') })
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [p, setP] = useState<any>(null)
  const [dec, setDec] = useState<Record<string, Record<string, { do: string; target_id?: string }>>>({ demos: {}, revenue: {} })
  const [addBds, setAddBds] = useState<string[]>([])
  const [summary, setSummary] = useState<any>(null)
  const sync = useSyncStatus()
  const live = !!sync.data?.enabled

  const upload = async () => {
    if (!file) return
    setBusy(true); setSummary(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await api.upload<any>('/api/import/preview', fd)
      setP(res)
      setAddBds(res.bd_proposals)
      const d: any = { demos: {}, revenue: {} }
      for (const k of ['demos', 'revenue']) for (const row of res[k]) d[k][row.row] = { do: row.action === 'add' ? 'add' : 'skip' }
      setDec(d)
    } catch (e) { toast({ tone: 'red', title: 'Could not read workbook', body: errorText(e) }) } finally { setBusy(false) }
  }
  const setRow = (kind: string, row: number, v: { do: string; target_id?: string }) => setDec((d) => ({ ...d, [kind]: { ...d[kind], [row]: v } }))
  const count = (kind: string, what: string) => Object.values(dec[kind] || {}).filter((x) => x.do === what).length
  const apply = async () => {
    const msg = <>You are about to apply: <b>{count('demos', 'add')}</b> new demos, <b>{count('demos', 'update')}</b> demo updates, <b>{count('revenue', 'add')}</b> new revenue records, <b>{count('revenue', 'update')}</b> revenue updates{addBds.length ? <>, and add BDs: <b>{addBds.join(', ')}</b></> : null}. Everything else is skipped. Existing records are only changed where you ticked “update”.</>
    if (!(await confirm({ title: 'Apply import?', body: msg, confirm: 'Apply import' }))) return
    setBusy(true)
    try {
      const s = await api.post<any>(`/api/import/${p.id}/apply`, { decisions: dec, add_bds: addBds })
      setSummary(s); setP(null); setFile(null)
      refresh()
    } catch (e) { toast({ tone: 'red', title: 'Import failed', body: errorText(e) }) } finally { setBusy(false) }
  }
  const cancel = async () => { if (p) await api.post(`/api/import/${p.id}/cancel`).catch(() => {}); setP(null); history.refetch() }

  return (
    <div className="col" style={{ gap: 14 }}>
      {live && <div className="notice amber"><b>Live Google Sheet mode is on</b> — the app already reads the sheet automatically, so manual imports are disabled (they would be overwritten by the next sync). You can still preview a file to check it. Turn live sync off in League settings to import manually.</div>}
      <div className="card">
        <div className="card-head"><FileSpreadsheet size={18} /><h3>Import an .xlsx workbook</h3></div>
        <div className="small muted" style={{ marginBottom: 10 }}>Reads <span className="kbd">Demos_and_Pipelines</span> (13 tracked columns) and <span className="kbd">League_Revenue</span> (13 columns). Matching uses BD + customer + demo date (demos) and BD + customer + opportunity (revenue) — never row numbers. New rows are added; existing rows are only updated where you tick them; blank cells never erase saved data; uncertain matches wait for your decision.</div>
        <div className="row wrap">
          <input type="file" accept=".xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} style={{ maxWidth: 420 }} />
          <button className="btn primary" disabled={!file || busy} onClick={upload}><Upload size={14} /> {busy ? 'Reading…' : 'Preview import'}</button>
        </div>
      </div>

      {summary && (
        <div className="card gold-edge"><div className="card-head"><h3>Import summary</h3></div>
          {summary.bds_added.length > 0 && <div>BDs added: <b>{summary.bds_added.join(', ')}</b></div>}
          {(['demos', 'revenue'] as const).map((k) => <div key={k}><b className="upper small">{k}</b>: {summary[k].added} added · {summary[k].updated} updated · {summary[k].skipped} skipped · {summary[k].rejected} rejected
            {summary[k].errors.length > 0 && <ul className="small red">{summary[k].errors.map((e: string) => <li key={e}>{e}</li>)}</ul>}</div>)}
        </div>
      )}

      {p && (
        <div className="card">
          <div className="card-head"><h3>Preview · {file?.name}</h3><span className="spacer" />
            <button className="btn" onClick={cancel}>Cancel</button>
            <button className="btn primary" disabled={busy || live} onClick={apply}>Apply import…</button></div>
          {p.previously_imported && <div className="notice amber" style={{ marginBottom: 10 }}>This exact file was already imported on {fmtDateTime(p.previously_imported.at)}. Re-importing is safe — unchanged rows are skipped.</div>}
          <div className="small muted">Sheets found: {p.sheets_found.join(', ')}. Not imported: {p.ignored_sheets.join(', ') || '—'}.</div>
          {p.sheet_issues.map((i: any, n: number) => <div key={n} className={`notice ${i.level === 'error' ? '' : 'amber'}`} style={{ marginTop: 8, ...(i.level === 'error' ? { background: 'var(--red-bg)', borderColor: 'rgba(200,30,30,.25)', color: 'var(--red)' } : {}) }}><b>{i.sheet}</b>: {i.message}</div>)}
          {p.bd_proposals.length > 0 && (
            <div className="notice gold" style={{ marginTop: 10 }}>BD names found in the workbook that are not configured yet — tick to add them:
              <div className="row wrap" style={{ marginTop: 6 }}>{p.bd_proposals.map((n: string) => (
                <label key={n} className="row small"><input type="checkbox" checked={addBds.includes(n)} onChange={(e) => setAddBds((a) => e.target.checked ? [...a, n] : a.filter((x) => x !== n))} /> {n}</label>))}</div></div>
          )}
          {(['demos', 'revenue'] as const).map((kind) => (
            <div key={kind} style={{ marginTop: 16 }}>
              <div className="row wrap"><h3 className="display" style={{ fontSize: 20 }}>{kind === 'demos' ? 'Demos_and_Pipelines' : 'League_Revenue'}</h3>
                {Object.entries(p[`${kind}_counts`] || {}).map(([k, v]) => <span key={k} className={`pill ${k === 'add' ? 'green' : k === 'update' ? 'blue' : k === 'rejected' ? 'red' : k === 'review' || k === 'duplicate' ? 'amber' : 'grey'}`}>{k}: {v as number}</span>)}
                <span className="spacer" />
                {p[kind].some((r: any) => r.action === 'update') && <button className="btn sm" onClick={() => p[kind].filter((r: any) => r.action === 'update').forEach((r: any) => setRow(kind, r.row, { do: 'update' }))}>Tick all updates</button>}
              </div>
              {p[kind].length === 0 ? <div className="small muted" style={{ marginTop: 6 }}>No data rows.</div> : (
                <div className="table-wrap" style={{ maxHeight: 420, marginTop: 8 }}><table className="data">
                  <thead><tr><th>Row</th><th>Record</th><th>Proposed</th><th>Decision</th><th>Details</th></tr></thead>
                  <tbody>{p[kind].filter((r: any) => r.action !== 'unchanged').map((r: any) => (
                    <tr key={r.row}>
                      <td className="dim">{r.row}</td><td style={{ fontWeight: 600 }}>{r.label}</td>
                      <td><span className={`pill ${r.action === 'add' ? 'green' : r.action === 'update' ? 'blue' : r.action === 'rejected' ? 'red' : 'amber'}`}>{r.action}</span></td>
                      <td>{r.action === 'rejected' || r.action === 'duplicate' ? <span className="dim small">skipped</span>
                        : r.action === 'review' ? (
                          <select value={dec[kind][r.row]?.target_id ? `u:${dec[kind][r.row].target_id}` : dec[kind][r.row]?.do} style={{ minHeight: 30, padding: '3px 6px' }}
                            onChange={(e) => { const v = e.target.value; setRow(kind, r.row, v.startsWith('u:') ? { do: 'update', target_id: v.slice(2) } : { do: v }) }}>
                            <option value="skip">Skip</option><option value="add">Add as new</option>
                            {r.candidates.map((c: any) => <option key={c.id} value={`u:${c.id}`}>Update {c.bd_name} · {c.customer_name} {c.demo_date ?? c.opportunity_name ?? ''}</option>)}
                          </select>)
                          : r.action === 'update' ? <label className="row small"><input type="checkbox" checked={dec[kind][r.row]?.do === 'update'} onChange={(e) => setRow(kind, r.row, { do: e.target.checked ? 'update' : 'skip' })} /> apply update</label>
                            : <label className="row small"><input type="checkbox" checked={dec[kind][r.row]?.do === 'add'} onChange={(e) => setRow(kind, r.row, { do: e.target.checked ? 'add' : 'skip' })} /> add</label>}</td>
                      <td className="small">
                        {Object.entries(r.diff || {}).map(([f, d]: any) => <div key={f}>{f}: <span className="diff-from">{String(d.from ?? '—')}</span> → <span className="diff-to">{String(d.to)}</span></div>)}
                        {Object.keys(r.kept || {}).length > 0 && <div className="dim">kept (blank in file): {Object.keys(r.kept).join(', ')}</div>}
                        {r.errors.map((e: string) => <div key={e} className="red">✕ {e}</div>)}
                        {r.warnings.map((w: string) => <div key={w} className="amber">! {w}</div>)}
                      </td>
                    </tr>))}</tbody>
                </table></div>)}
              {p[kind].some((r: any) => r.action === 'unchanged') && <div className="tiny dim" style={{ marginTop: 4 }}>{p[kind].filter((r: any) => r.action === 'unchanged').length} unchanged row(s) hidden — already in the database.</div>}
            </div>
          ))}
        </div>
      )}

      <div className="card"><div className="card-head"><h3>Import history</h3><button className="btn sm ghost" onClick={() => history.refetch()}><RefreshCw size={13} /></button></div>
        {!history.data?.length ? <Empty>No imports yet.</Empty> : <div className="table-wrap"><table className="data">
          <thead><tr><th>#</th><th>File</th><th>Status</th><th>Uploaded</th><th>By</th><th>Result</th></tr></thead>
          <tbody>{history.data.map((h) => <tr key={h.id}><td>{h.id}</td><td>{h.filename}</td><td><span className={`pill ${h.status === 'applied' ? 'green' : h.status === 'cancelled' ? 'grey' : 'amber'}`}>{h.status}</span></td>
            <td className="small">{fmtDateTime(h.created_at)}</td><td>{h.by}</td>
            <td className="small">{h.summary ? `Demos +${h.summary.demos.added}/~${h.summary.demos.updated} · Revenue +${h.summary.revenue.added}/~${h.summary.revenue.updated}` : '—'}</td></tr>)}</tbody></table></div>}
      </div>
    </div>
  )
}

/* ================================================================== export */
function Exports() {
  const toast = useToast()
  const items = [
    ['workbook', 'Complete consolidated workbook', 'Demos_and_Pipelines, League_Revenue, POC_Tracker, BD_Performance, Daily_Targets and official leaderboards'],
    ['demos', 'Demo Tracker', 'Demos_and_Pipelines — 13 columns with dropdowns and the live Time Remaining formula'],
    ['revenue', 'Revenue Tracker', 'League_Revenue — the finalised 13 columns'],
    ['poc', 'POC Tracker', 'Demos currently in a POC status'],
    ['performance', 'BD Performance', 'Per-BD summary and the day-by-day target / carry-forward ledger'],
    ['leaderboards', 'Official Leaderboards', 'Overall, F2F, Revenue and weekly standings (full league data)'],
  ]
  return (
    <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(300px, 100%), 1fr))' }}>
      {items.map(([k, t, d]) => (
        <div key={k} className="card col" style={{ gap: 8 }}>
          <div className="row"><FileSpreadsheet size={18} color="var(--green)" /><h3 className="display" style={{ fontSize: 20 }}>{t}</h3></div>
          <div className="small muted" style={{ flex: 1 }}>{d}</div>
          <button className="btn" onClick={() => download(`/api/export/${k}`).catch((e) => toast({ tone: 'red', title: 'Export failed', body: errorText(e) }))}><Download size={14} /> Download .xlsx</button>
        </div>))}
      <div className="card col" style={{ gap: 8 }}><div className="row"><Filter size={18} color="var(--blue)" /><h3 className="display" style={{ fontSize: 20 }}>Filtered reports</h3></div>
        <div className="small muted">Use the “Filtered reports” tab and click “Export filtered results”.</div></div>
    </div>
  )
}

/* ================================================================== settings */
function SettingsForm() {
  const q = useQuery({ queryKey: ['settings'], queryFn: () => api.get<any>('/api/settings') })
  const toast = useToast()
  const refresh = useRefreshAll()
  const confirm = useConfirm()
  const { setting: rm } = useReducedMotion()
  const [s, setS] = useState<any>(null)
  const [arenaUrl, setArenaUrl] = useState<string | null>(null)
  const [pw, setPw] = useState({ current_password: '', new_password: '' })
  useEffect(() => { if (q.data) setS(structuredClone(q.data)) }, [q.data])
  if (!s) return <Loading />
  const set = (k: string, v: any) => setS((x: any) => ({ ...x, [k]: v }))
  const save = async () => {
    const { arena_link_enabled: _ignored, ...body } = s
    try {
      const r = await api.put<any>('/api/settings', body)
      toast({ tone: 'green', title: 'Settings saved', body: r.changed.length ? `Changed: ${r.changed.join(', ')}` : 'No changes' })
      q.refetch(); refresh()
    } catch (e) { toast({ tone: 'red', title: 'Not saved', body: errorText(e) }) }
  }
  const genArena = async () => {
    if (s.arena_link_enabled && !(await confirm({ title: 'Generate a new Arena link?', body: 'The previous display link stops working.' }))) return
    const r = await api.post<{ token: string }>('/api/settings/arena-link')
    setArenaUrl(`${location.origin}/arena?token=${r.token}`)
    q.refetch()
  }
  return (
    <div className="col" style={{ gap: 14 }}>
      <SheetSettings s={s} set={set} />
      <div className="row"><span className="spacer" /><button className="btn primary" onClick={save}><Save size={14} /> Save settings</button></div>
      <div className="card">
        <div className="card-head"><h3>League calendar & daily target</h3></div>
        <div className="form-grid">
          <label className="field">League name<input value={s.league_name} onChange={(e) => set('league_name', e.target.value)} /></label>
          <label className="field">League start<input type="date" value={s.league_start} onChange={(e) => set('league_start', e.target.value)} /></label>
          <label className="field">League end<input type="date" value={s.league_end} onChange={(e) => set('league_end', e.target.value)} /></label>
          <label className="field">Office login<input type="time" value={s.office_login_time} onChange={(e) => set('office_login_time', e.target.value)} /></label>
          <label className="field">Stand-up<input type="time" value={s.standup_time} onChange={(e) => set('standup_time', e.target.value)} /></label>
          <label className="field">End-of-day cutoff (auto close)<input type="time" value={s.day_cutoff_time} onChange={(e) => set('day_cutoff_time', e.target.value)} /></label>
          <label className="field">Week starts on<select value={s.week_start_day} onChange={(e) => set('week_start_day', Number(e.target.value))}>
            {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map((d, i) => <option key={d} value={i}>{d}</option>)}</select></label>
          <label className="field">Time zone<input value={s.timezone} onChange={(e) => set('timezone', e.target.value)} /></label>
        </div>
        <div className="tiny dim" style={{ marginTop: 8 }}>Working days are Monday–Saturday; Sunday is the weekly holiday. Daily target = 1 qualified completed demo + any pending carry-forward. A day is finalised at the cutoff or when you close it from the dashboard.</div>
      </div>
      <div className="card">
        <div className="card-head"><h3>F2F challenge & revenue</h3></div>
        <div className="form-grid">
          <label className="field">F2F target<input type="number" min={1} value={s.f2f_target} onChange={(e) => set('f2f_target', Number(e.target.value))} /></label>
          <label className="field">F2F milestones (comma separated)<input value={s.f2f_milestones.join(', ')} onChange={(e) => set('f2f_milestones', e.target.value.split(',').map((x) => Number(x.trim())).filter((x) => x > 0))} /></label>
          <label className="field">Revenue award threshold (₹)<input type="number" min={0} value={s.revenue_threshold_inr} onChange={(e) => set('revenue_threshold_inr', Number(e.target.value))} /></label>
        </div>
        <div className="section-label" style={{ marginTop: 16 }}>Region matching (Country field → F2F region)</div>
        <div className="form-grid">
          {Object.entries(s.f2f_regions as Record<string, string[]>).map(([r, aliases]) => (
            <label key={r} className="field">{r}<textarea rows={4} value={aliases.join(', ')} onChange={(e) => set('f2f_regions', { ...s.f2f_regions, [r]: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })} /></label>))}
        </div>
        <div className="tiny dim" style={{ marginTop: 6 }}>A demo's Country matches a region if the whole value or any comma-separated part equals one of these (case-insensitive), e.g. “Singapore, USA” → Singapore.</div>
      </div>
      <div className="card">
        <div className="card-head"><h3>Prizes</h3></div>
        <div className="form-grid">
          {Object.entries(s.awards as Record<string, any>).map(([k, a]) => (
            <label key={k} className="field">{a.title}<input value={a.prize ?? ''} placeholder="Not confirmed" onChange={(e) => set('awards', { ...s.awards, [k]: { ...a, prize: e.target.value || null } })} /></label>))}
        </div>
      </div>
      <div className="card">
        <div className="card-head"><h3>Motivational messages</h3><span className="hint">One per line — rotated on the dashboard and Arena</span></div>
        <textarea rows={6} value={s.motivational_messages.join('\n')} onChange={(e) => set('motivational_messages', e.target.value.split('\n'))} onBlur={() => set('motivational_messages', s.motivational_messages.map((m: string) => m.trim()).filter(Boolean))} />
      </div>
      <div className="row"><span className="spacer" /><button className="btn primary" onClick={save}><Save size={14} /> Save settings</button></div>

      <div className="card">
        <div className="card-head"><h3>League Arena display link</h3></div>
        <div className="small muted">Open <span className="kbd">/arena</span> on the office TV. If the TV isn't signed in, use a read-only display link (shows standings only — no editing, no other data).</div>
        <div className="row wrap" style={{ marginTop: 10 }}>
          <label className="field" style={{ width: 200 }}>Auto-refresh (seconds)<input type="number" min={10} value={s.arena_refresh_seconds} onChange={(e) => set('arena_refresh_seconds', Number(e.target.value))} /></label>
          <button className="btn" onClick={genArena}><Plus size={14} /> {s.arena_link_enabled ? 'Regenerate display link' : 'Create display link'}</button>
          {s.arena_link_enabled && <button className="btn danger" onClick={async () => { await api.del('/api/settings/arena-link'); setArenaUrl(null); q.refetch() }}>Revoke link</button>}
        </div>
        {arenaUrl && <div className="notice gold" style={{ marginTop: 10, wordBreak: 'break-all' }}>Copy this now — it is shown only once:<br /><b>{arenaUrl}</b></div>}
      </div>

      <div className="card">
        <div className="card-head"><h3>This browser</h3></div>
        <label className="field" style={{ maxWidth: 320 }}>Reduced motion
          <select value={rm} onChange={(e) => setReducedMotion(e.target.value as any)}>
            <option value="system">Follow system setting</option><option value="on">On — minimal animation</option><option value="off">Off — full animations</option></select></label>
      </div>

      <div className="card">
        <div className="card-head"><h3>Change admin password</h3></div>
        <div className="form-grid">
          <label className="field">Current password<input type="password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></label>
          <label className="field">New password (min 10)<input type="password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></label>
        </div>
        <div className="row" style={{ marginTop: 10 }}><span className="spacer" />
          <button className="btn" disabled={pw.new_password.length < 10 || !pw.current_password} onClick={async () => {
            try { await api.post('/api/auth/password', pw); toast({ tone: 'green', title: 'Password changed' }); setPw({ current_password: '', new_password: '' }) } catch (e) { toast({ tone: 'red', title: 'Not changed', body: errorText(e) }) }
          }}>Update password</button></div>
      </div>
    </div>
  )
}

/* ================================================================== BDs */
function BDMembers() {
  const q = useQuery({ queryKey: ['bds'], queryFn: () => api.get<any[]>('/api/bds') })
  const toast = useToast()
  const refresh = useRefreshAll()
  const [name, setName] = useState('')
  const [edits, setEdits] = useState<Record<number, any>>({})
  if (!q.data) return <Loading />
  const save = async (b: any) => {
    try { await api.put(`/api/bds/${b.id}`, { ...b, ...edits[b.id] }); setEdits((e) => ({ ...e, [b.id]: undefined })); refresh() } catch (e) { toast({ tone: 'red', title: 'Not saved', body: errorText(e) }) }
  }
  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="notice">The BD master list was read from the workbook's BD dropdown. Inactive BDs are hidden from leaderboards and new-record forms but their history is kept.</div>
      <div className="table-wrap"><table className="data">
        <thead><tr><th>Order</th><th>Name</th><th>Active</th><th></th></tr></thead>
        <tbody>{q.data.map((b) => {
          const e = { ...b, ...edits[b.id] }
          const dirty = !!edits[b.id]
          const upd = (k: string, v: any) => setEdits((x) => ({ ...x, [b.id]: { ...x[b.id], [k]: v } }))
          return <tr key={b.id}><td style={{ width: 90 }}><input type="number" value={e.display_order} onChange={(ev) => upd('display_order', Number(ev.target.value))} /></td>
            <td><input value={e.name} onChange={(ev) => upd('name', ev.target.value)} /></td>
            <td><input type="checkbox" checked={e.active} onChange={(ev) => upd('active', ev.target.checked)} /></td>
            <td>{dirty && <button className="btn sm primary" onClick={() => save(b)}>Save</button>}</td></tr>
        })}</tbody></table></div>
      <div className="row" style={{ maxWidth: 480 }}>
        <input placeholder="New BD name" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="btn" disabled={!name.trim()} onClick={async () => {
          try { await api.post('/api/bds', { name }); setName(''); refresh() } catch (e) { toast({ tone: 'red', title: 'Not added', body: errorText(e) }) }
        }}><Plus size={14} /> Add BD</button>
      </div>
    </div>
  )
}

/* ================================================================== audit */
function AuditLog() {
  const [entity, setEntity] = useState('')
  const q = useQuery({ queryKey: ['audit', entity], queryFn: () => api.get<any[]>(`/api/audit?limit=500${entity ? `&entity=${entity}` : ''}`) })
  const show = (v: any) => (v == null ? '' : Object.entries(v).map(([k, x]) => `${k}: ${typeof x === 'object' ? JSON.stringify(x) : x}`).join(' · '))
  return (
    <div className="col" style={{ gap: 12 }}>
      <div className="row"><select style={{ width: 220 }} value={entity} onChange={(e) => setEntity(e.target.value)}>
        <option value="">All entities</option>{['demo', 'revenue', 'import', 'settings', 'bd', 'exchange_rate', 'award', 'day', 'export', 'auth'].map((x) => <option key={x}>{x}</option>)}</select>
        <span className="small muted">Who changed what, and when. Most recent first.</span></div>
      {!q.data ? <Loading /> : !q.data.length ? <Empty>No audit entries.</Empty> : (
        <div className="table-wrap" style={{ maxHeight: 640 }}><table className="data">
          <thead><tr><th>When</th><th>Who</th><th>Entity</th><th>Action</th><th>Before</th><th>After</th><th>Note</th></tr></thead>
          <tbody>{q.data.map((a) => <tr key={a.id}><td className="nowrap small">{fmtDateTime(a.at)}</td><td>{a.actor}</td><td>{a.entity}</td><td><span className="pill grey">{a.action}</span></td>
            <td className="small diff-from" style={{ textDecoration: 'none', maxWidth: 320, wordBreak: 'break-word' }}>{show(a.before)}</td>
            <td className="small" style={{ maxWidth: 380, wordBreak: 'break-word' }}>{show(a.after)}</td><td className="small">{a.note}</td></tr>)}</tbody>
        </table></div>)}
    </div>
  )
}
