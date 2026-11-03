import { Pencil, Plus, RotateCcw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, errorText } from '../api'
import { RevenueBoard } from '../components/board'
import { EMPTY_HIGHLIGHTS } from '../components/celebrate'
import { HBars } from '../components/charts'
import { RevenueForm } from '../components/forms'
import { LiveLockNotice, SyncBadge } from '../components/sync'
import { Empty, Loading, Tabs, useConfirm, useToast } from '../components/ui'
import { useMeta, useRefreshAll, useRevenue, useSnapshot } from '../hooks'
import { fmtDate, fmtDateTime, fmtINR, fmtLakh, fmtMoney } from '../lib/format'
import type { Revenue } from '../types'


export default function RevenueTracker() {
  const [tab, setTab] = useState<'records' | 'breakdown' | 'rates' | 'trash'>('records')
  return (
    <>
      <div className="page-head"><div><h1>Revenue Tracker</h1><div className="sub">League_Revenue · Signed or Amount Credited · each opportunity counted once</div></div></div>
      <div style={{ marginBottom: 12 }}><SyncBadge /></div>
      <Tabs value={tab} onChange={setTab} tabs={[{ key: 'records', label: 'Records' }, { key: 'breakdown', label: 'Breakdown & leaderboard' }, { key: 'rates', label: 'Exchange rates' }, { key: 'trash', label: 'Deleted' }]} />
      {tab === 'records' && <Records />}
      {tab === 'breakdown' && <Breakdown />}
      {tab === 'rates' && <Rates />}
      {tab === 'trash' && <Trash />}
    </>
  )
}

function Records() {
  const { data, isLoading } = useRevenue()
  const refresh = useRefreshAll()
  const confirm = useConfirm()
  const [edit, setEdit] = useState<Revenue | null | undefined>(undefined)
  const { data: meta } = useMeta()
  const live = !!meta?.live_mode
  if (isLoading) return <Loading />
  const total = (data ?? []).reduce((s, r) => s + (r.evaluation.eligible ? r.evaluation.inr_value ?? 0 : 0), 0)
  const del = async (r: Revenue) => {
    if (!(await confirm({ title: 'Delete revenue record?', danger: true, confirm: 'Move to Deleted', body: <>{r.customer_name} – {r.opportunity_name} ({fmtMoney(r.currency, r.contract_value)}) will be removed from revenue totals. You can restore it later.</> }))) return
    await api.del(`/api/revenue/${r.id}`)
    refresh()
  }
  return (
    <div className="col" style={{ gap: 12 }}>
      <LiveLockNotice what="Revenue records" />
      <div className="row wrap">
        <div className="kpi" style={{ minWidth: 220 }}><div className="label">Confirmed league revenue</div><div className="value green">{fmtINR(total)}</div></div>
        <span className="spacer" />
        {!live && <button className="btn primary" onClick={() => setEdit(null)}><Plus size={16} /> Record revenue</button>}
      </div>
      {!data?.length ? <Empty>No revenue recorded yet. Use “Record revenue” or import the League_Revenue sheet.</Empty> : (
        <div className="table-wrap"><table className="data">
          <thead><tr><th>Sl</th><th>BD</th><th>Customer</th><th>Country</th><th>Domain</th><th>Opportunity</th><th>Status</th><th>Currency</th><th className="num">Value</th>
            <th>Signed</th><th>Credited</th><th>Onboarding</th><th className="num">INR (league)</th><th>Eligibility</th><th>Remarks</th><th></th></tr></thead>
          <tbody>{data.map((r) => (
            <tr key={r.id} className={r.evaluation.eligible ? '' : 'muted-row'}>
              <td className="dim">{r.sl_no}</td><td style={{ fontWeight: 600 }}>{r.bd_name}</td><td style={{ fontWeight: 600 }}>{r.customer_name}</td>
              <td className="small">{r.country}</td><td className="small">{r.domain}</td><td>{r.opportunity_name}</td>
              <td><span className={`pill ${r.contract_status === 'Signed' ? 'blue' : 'green'}`}>{r.contract_status}</span></td>
              <td>{r.currency}</td><td className="num">{r.contract_value.toLocaleString(r.currency === 'INR' ? 'en-IN' : 'en-US')}</td>
              <td className="nowrap">{fmtDate(r.contract_signed_date)}</td><td className="nowrap">{fmtDate(r.amount_credited_date)}</td><td className="nowrap">{fmtDate(r.customer_onboarding_date)}</td>
              <td className="num">{r.evaluation.inr_value != null ? fmtINR(r.evaluation.inr_value) : '—'}
                {r.currency !== 'INR' && r.evaluation.rate_used && <div className="tiny dim">@{r.evaluation.rate_used} · {r.evaluation.rate_date}</div>}</td>
              <td>{r.evaluation.eligible ? <span className="pill green">Counted</span>
                : r.evaluation.pending_conversion ? <span className="pill amber" title={r.evaluation.reason ?? ''}>Pending conversion</span>
                  : <span className="pill grey" title={r.evaluation.reason ?? ''}>{r.evaluation.reason}</span>}</td>
              <td className="small" style={{ maxWidth: 220 }}>{r.remarks}</td>
              <td className="nowrap"><button className="btn sm ghost" onClick={() => setEdit(r)} aria-label="Edit"><Pencil size={14} /></button>
                {!live && <button className="btn sm ghost" onClick={() => del(r)} aria-label="Delete"><Trash2 size={14} /></button>}</td>
            </tr>))}</tbody>
        </table></div>
      )}
      {edit !== undefined && <RevenueForm rec={edit} onClose={() => setEdit(undefined)} />}
    </div>
  )
}

function Breakdown() {
  const { data: s } = useSnapshot()
  if (!s) return <Loading />
  const toRows = (o: Record<string, number>) => Object.entries(o).map(([name, value]) => ({ name, value }))
  return (
    <div className="col" style={{ gap: 16 }}>
      <div className="card"><div className="card-head"><h2>Revenue Champion leaderboard</h2><span className="tag-provisional">Official · provisional</span></div>
        <RevenueBoard rev={s.revenue} hl={EMPTY_HIGHLIGHTS} /></div>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(380px, 100%), 1fr))' }}>
        <div className="card"><div className="card-head"><h3>By country</h3></div><HBars data={toRows(s.revenue.by_country)} format={fmtLakh} /></div>
        <div className="card"><div className="card-head"><h3>By domain</h3></div><HBars data={toRows(s.revenue.by_domain ?? {})} format={fmtLakh} /></div>
        <div className="card"><div className="card-head"><h3>By contract status</h3></div><HBars data={toRows(s.revenue.by_status)} format={fmtLakh} /></div>
        <div className="card"><div className="card-head"><h3>By BD</h3></div><HBars data={s.revenue.per_bd.map((r) => ({ name: r.bd_name, value: r.total_inr }))} format={fmtLakh} /></div>
      </div>
    </div>
  )
}

function Rates() {
  const rates = useQuery({ queryKey: ['rates'], queryFn: () => api.get<any[]>('/api/rates') })
  const refresh = useRefreshAll()
  const toast = useToast()
  const confirm = useConfirm()
  const [f, setF] = useState({ currency: 'USD', rate_to_inr: '', effective_date: '', basis: '' })
  const save = async () => {
    try {
      await api.post('/api/rates', { ...f, rate_to_inr: Number(f.rate_to_inr) })
      toast({ tone: 'green', title: `${f.currency} rate saved` })
      setF({ ...f, rate_to_inr: '', basis: '' })
      refresh()
    } catch (e) { toast({ tone: 'red', title: 'Rate not saved', body: errorText(e) }) }
  }
  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="notice">Rates are never assumed. A non-INR record converts using the latest rate for its currency whose <b>effective date is on or before</b> the record's eligibility date (Signed date or Credited date). Without one, it is flagged <b>pending conversion</b> and excluded from INR rankings. Each record shows the rate and date it used.</div>
      <div className="card"><div className="card-head"><h3>Add / update a rate</h3></div>
        <div className="form-grid">
          <label className="field">Currency<input value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value.toUpperCase() })} /></label>
          <label className="field">1 unit = ₹<input type="number" step="0.0001" min="0" value={f.rate_to_inr} onChange={(e) => setF({ ...f, rate_to_inr: e.target.value })} /></label>
          <label className="field">Effective date<input type="date" value={f.effective_date} onChange={(e) => setF({ ...f, effective_date: e.target.value })} /></label>
          <label className="field">Basis / source<input placeholder="e.g. RBI reference rate" value={f.basis} onChange={(e) => setF({ ...f, basis: e.target.value })} /></label>
        </div>
        <div className="row" style={{ marginTop: 12 }}><span className="spacer" /><button className="btn primary" disabled={!f.currency || !f.rate_to_inr || !f.effective_date || f.basis.length < 2} onClick={save}>Save rate</button></div>
      </div>
      {!rates.data?.length ? <Empty>No exchange rates configured.</Empty> : (
        <div className="table-wrap"><table className="data">
          <thead><tr><th>Currency</th><th className="num">Rate to INR</th><th>Effective</th><th>Basis</th><th>Added by</th><th>Added</th><th></th></tr></thead>
          <tbody>{rates.data.map((r) => (
            <tr key={r.id}><td>{r.currency}</td><td className="num">{r.rate_to_inr}</td><td>{fmtDate(r.effective_date)}</td><td>{r.basis}</td><td>{r.created_by}</td><td className="small">{fmtDateTime(r.created_at)}</td>
              <td><button className="btn sm ghost" onClick={async () => {
                if (await confirm({ title: 'Delete rate?', danger: true, body: 'Records using it will become pending conversion unless another rate applies.' })) { await api.del(`/api/rates/${r.id}`); refresh() }
              }}><Trash2 size={14} /></button></td></tr>))}</tbody>
        </table></div>
      )}
    </div>
  )
}

function Trash() {
  const { data, isLoading } = useRevenue(true)
  const { data: meta } = useMeta()
  const refresh = useRefreshAll()
  if (isLoading) return <Loading />
  if (!data?.length) return <Empty>No deleted revenue records.</Empty>
  return (
    <div className="table-wrap"><table className="data">
      <thead><tr><th>Customer</th><th>Opportunity</th><th>BD</th><th className="num">Value</th><th>Deleted</th><th></th></tr></thead>
      <tbody>{data.map((r) => (
        <tr key={r.id}><td>{r.customer_name}</td><td>{r.opportunity_name}</td><td>{r.bd_name}</td><td className="num">{fmtMoney(r.currency, r.contract_value)}</td>
          <td className="small">{fmtDateTime(r.deleted_at)}</td>
          <td>{meta?.live_mode ? <span className="tiny dim">Add the row back in the sheet to restore</span> : <button className="btn sm" onClick={async () => { await api.post(`/api/revenue/${r.id}/restore`); refresh() }}><RotateCcw size={14} /> Restore</button>}</td></tr>))}</tbody>
    </table></div>
  )
}
