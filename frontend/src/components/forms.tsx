import { useState } from 'react'
import { ApiError, api, errorText } from '../api'
import { useMeta, useRefreshAll } from '../hooks'
import type { Demo, Revenue } from '../types'
import { Modal, useToast } from './ui'

const TZ = ['IST', 'SGT', 'MYT', 'GST', 'AST', 'AEST', 'AEDT', 'AWST', 'NZST', 'NZDT', 'GMT', 'BST', 'UTC', 'CET', 'CEST', 'EST', 'EDT', 'CST', 'PST', 'PDT', 'ICT', 'WIB', 'PHT']

function Datalist({ id, options }: { id: string; options: string[] }) {
  return <datalist id={id}>{options.map((o) => <option key={o} value={o} />)}</datalist>
}

/* ------------------------------------------------------------------ demo */
export function DemoForm({ demo, onClose }: { demo?: Demo | null; onClose: () => void }) {
  const { data: meta } = useMeta()
  const refresh = useRefreshAll()
  const toast = useToast()
  const [f, setF] = useState(() => ({
    bd_id: demo?.bd_id ?? '', customer_name: demo?.customer_name ?? '', domain: demo?.domain ?? '', country: demo?.country ?? '',
    demo_type: demo?.demo_type ?? '', demo_on: demo?.demo_on ?? 'Product Demo', demo_date: demo?.demo_date ?? '',
    demo_time: demo?.demo_time ?? '', time_zone: demo?.time_zone ?? 'IST', status: demo?.status ?? 'Scheduled',
    qualified: demo?.qualified ?? '', poc_started_on: demo?.poc_started_on ?? '', poc_remarks: demo?.poc_remarks ?? '',
    sl_no: demo?.sl_no ?? null,
  }))
  const [errs, setErrs] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const set = (k: string, v: any) => setF((x) => ({ ...x, [k]: v }))
  const locked = !!meta?.live_mode
  const canQualify = f.status === 'Completed' || (meta?.poc_statuses ?? []).includes(f.status)
  const isPoc = (meta?.poc_statuses ?? []).includes(f.status)

  const save = async () => {
    setBusy(true)
    setErrs([])
    const body = {
      ...f, bd_id: Number(f.bd_id), demo_type: f.demo_type || null, qualified: canQualify ? f.qualified || null : f.qualified === 'Yes' ? null : f.qualified || null,
      demo_date: f.demo_date || null, demo_time: f.demo_time || null, poc_started_on: f.poc_started_on || null,
      domain: f.domain || null, country: f.country || null, time_zone: f.time_zone || null, poc_remarks: f.poc_remarks || null,
    }
    try {
      if (demo) await api.put(`/api/demos/${demo.id}`, body)
      else await api.post('/api/demos', body)
      toast({ tone: 'green', title: demo ? 'Demo updated' : 'Demo added', body: `${f.customer_name}` })
      refresh()
      onClose()
    } catch (e) {
      setErrs(e instanceof ApiError && e.detail?.errors ? e.detail.errors : [errorText(e)])
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={demo ? `Edit demo · ${demo.customer_name}` : 'Add demo'} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" onClick={save} disabled={busy || !f.bd_id || !f.customer_name || (locked && !isPoc)}>{busy ? 'Saving…' : 'Save'}</button>
    </>}>
      {locked && <div className="notice" style={{ marginBottom: 12 }}>Live Google Sheet mode: demo fields are read-only here — change them in the sheet.{isPoc ? ' POC start date and remarks below are app-only and can be edited.' : ''}</div>}
      <fieldset className="plain" disabled={locked}>
      <div className="form-grid">
        <label className="field">BD <span className="req">*</span>
          <select value={f.bd_id} onChange={(e) => set('bd_id', e.target.value)}>
            <option value="">Select BD…</option>
            {meta?.bds.filter((b) => b.active || b.id === demo?.bd_id).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select></label>
        <label className="field">Customer Name <span className="req">*</span><input value={f.customer_name} onChange={(e) => set('customer_name', e.target.value)} /></label>
        <label className="field">Domain<input list="dl-domain" value={f.domain} onChange={(e) => set('domain', e.target.value)} /></label>
        <label className="field">Country<input list="dl-country" value={f.country} onChange={(e) => set('country', e.target.value)} placeholder="e.g. Malaysia, Dubai" /></label>
        <label className="field">Demo Type
          <div className="seg">{['F2F', 'Virtual'].map((t) => <button type="button" key={t} className={f.demo_type === t ? 'on' : ''} onClick={() => set('demo_type', f.demo_type === t ? '' : t)}>{t}</button>)}</div></label>
        <label className="field">Demo On<input list="dl-demoon" value={f.demo_on} onChange={(e) => set('demo_on', e.target.value)} /></label>
        <label className="field">Demo Date{f.status === 'Completed' && <span className="req"> * (completion date)</span>}<input type="date" value={f.demo_date} onChange={(e) => set('demo_date', e.target.value)} /></label>
        <label className="field">Demo Time<input type="time" value={f.demo_time} onChange={(e) => set('demo_time', e.target.value)} /></label>
        <label className="field">Time Zone<input list="dl-tz" value={f.time_zone} onChange={(e) => set('time_zone', e.target.value)} /></label>
        <label className="field">Status <span className="req">*</span>
          <select value={f.status} onChange={(e) => {
            const st = e.target.value
            const pocs = meta?.poc_statuses ?? []
            setF((x) => ({ ...x, status: st, qualified: st === 'Completed' || pocs.includes(st) ? x.qualified : x.qualified === 'Yes' ? '' : x.qualified }))
          }}>{meta?.demo_statuses.map((s) => <option key={s}>{s}</option>)}</select></label>
        <label className="field">Qualified Demo
          <select value={f.qualified} onChange={(e) => set('qualified', e.target.value)}>
            <option value="">—</option>
            <option disabled={!canQualify}>Yes</option>
            <option>No</option>
          </select>
          {!canQualify && <span className="tiny dim">Only a Completed demo can be qualified</span>}</label>
      </div>
      </fieldset>
      <div className="form-grid" style={{ marginTop: isPoc ? 12 : 0 }}>
        {isPoc && <>
          <label className="field">POC Start Date<input type="date" value={f.poc_started_on} onChange={(e) => set('poc_started_on', e.target.value)} /></label>
          <label className="field" style={{ gridColumn: '1 / -1' }}>POC Remarks<textarea rows={2} value={f.poc_remarks} onChange={(e) => set('poc_remarks', e.target.value)} /></label>
        </>}
      </div>
      <div className="notice" style={{ marginTop: 14 }}>Counts toward the league only when <b>Status = Completed</b> and <b>Qualified = Yes</b>, dated within 1 Nov – 20 Dec 2026. The Demo Date is the completion date. Changing status updates this record — it never creates a second achievement.</div>
      {errs.length > 0 && <div className="errors" style={{ marginTop: 10 }}>{errs.map((e) => <div key={e}>• {e}</div>)}</div>}
      <Datalist id="dl-domain" options={meta?.domains ?? []} />
      <Datalist id="dl-country" options={meta?.countries ?? []} />
      <Datalist id="dl-demoon" options={meta?.demo_on_options ?? []} />
      <Datalist id="dl-tz" options={TZ} />
    </Modal>
  )
}

/* ------------------------------------------------------------------ revenue */
export function RevenueForm({ rec, onClose }: { rec?: Revenue | null; onClose: () => void }) {
  const { data: meta } = useMeta()
  const refresh = useRefreshAll()
  const toast = useToast()
  const [f, setF] = useState(() => ({
    bd_id: rec?.bd_id ?? '', customer_name: rec?.customer_name ?? '', country: rec?.country ?? '', domain: rec?.domain ?? '',
    opportunity_name: rec?.opportunity_name ?? '', contract_status: rec?.contract_status ?? 'Signed', currency: rec?.currency ?? 'INR',
    contract_value: rec?.contract_value?.toString() ?? '', contract_signed_date: rec?.contract_signed_date ?? '',
    amount_credited_date: rec?.amount_credited_date ?? '', customer_onboarding_date: rec?.customer_onboarding_date ?? '',
    remarks: rec?.remarks ?? '', fx_rate_override: rec?.fx_rate_override?.toString() ?? '', fx_rate_override_date: rec?.fx_rate_override_date ?? '',
    sl_no: rec?.sl_no ?? null,
  }))
  const [errs, setErrs] = useState<string[]>([])
  const [dups, setDups] = useState<any[] | null>(null)
  const locked = !!meta?.live_mode
  const [busy, setBusy] = useState(false)
  const set = (k: string, v: any) => setF((x) => ({ ...x, [k]: v }))

  const save = async (confirmNotDuplicate = false) => {
    setBusy(true)
    setErrs([])
    const nul = (v: string) => (v === '' ? null : v)
    const body = {
      ...f, bd_id: Number(f.bd_id), contract_value: Number(f.contract_value), country: nul(f.country), domain: nul(f.domain),
      contract_signed_date: nul(f.contract_signed_date), amount_credited_date: nul(f.amount_credited_date),
      customer_onboarding_date: nul(f.customer_onboarding_date), remarks: nul(f.remarks),
      fx_rate_override: f.fx_rate_override ? Number(f.fx_rate_override) : null, fx_rate_override_date: nul(f.fx_rate_override_date),
      confirm_not_duplicate: confirmNotDuplicate,
    }
    try {
      if (rec) await api.put(`/api/revenue/${rec.id}`, body)
      else await api.post('/api/revenue', body)
      toast({ tone: 'green', title: rec ? 'Revenue updated' : 'Revenue recorded', body: `${f.customer_name} · ${f.opportunity_name}` })
      refresh()
      onClose()
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setDups(e.detail?.duplicates ?? [])
      else setErrs(e instanceof ApiError && e.detail?.errors ? e.detail.errors : [errorText(e)])
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={rec ? `Edit revenue · ${rec.customer_name}` : 'Record revenue'} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" onClick={() => save(false)} disabled={busy || !f.bd_id || !f.customer_name || !f.opportunity_name || f.contract_value === '' || (locked && f.currency === 'INR')}>{busy ? 'Saving…' : 'Save'}</button>
    </>}>
      {locked && <div className="notice" style={{ marginBottom: 12 }}>Live Google Sheet mode: revenue fields are read-only here — change them in the sheet. A record-specific exchange rate (non-INR only) can still be set below.</div>}
      <fieldset className="plain" disabled={locked}>
      <div className="form-grid">
        <label className="field">BD <span className="req">*</span>
          <select value={f.bd_id} onChange={(e) => set('bd_id', e.target.value)}>
            <option value="">Select BD…</option>
            {meta?.bds.filter((b) => b.active || b.id === rec?.bd_id).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select></label>
        <label className="field">Customer Name <span className="req">*</span><input value={f.customer_name} onChange={(e) => set('customer_name', e.target.value)} /></label>
        <label className="field">Country<input list="dl-country2" value={f.country} onChange={(e) => set('country', e.target.value)} /></label>
        <label className="field">Domain<input list="dl-domain2" value={f.domain} onChange={(e) => set('domain', e.target.value)} /></label>
        <label className="field">Opportunity Name <span className="req">*</span><input list="dl-opp" value={f.opportunity_name} onChange={(e) => set('opportunity_name', e.target.value)} /></label>
        <label className="field">Contract Status <span className="req">*</span>
          <div className="seg">{['Signed', 'Amount Credited'].map((t) => <button type="button" key={t} className={f.contract_status === t ? 'on' : ''} onClick={() => set('contract_status', t)}>{t}</button>)}</div></label>
        <label className="field">Currency <span className="req">*</span><input list="dl-cur" value={f.currency} onChange={(e) => set('currency', e.target.value.toUpperCase())} /></label>
        <label className="field">Contract Value <span className="req">*</span><input type="number" min="0" step="0.01" value={f.contract_value} onChange={(e) => set('contract_value', e.target.value)} /></label>
        <label className="field">Contract Signed Date{f.contract_status === 'Signed' && <span className="req"> *</span>}<input type="date" value={f.contract_signed_date} onChange={(e) => set('contract_signed_date', e.target.value)} /></label>
        <label className="field">Amount Credited Date{f.contract_status === 'Amount Credited' && <span className="req"> *</span>}<input type="date" value={f.amount_credited_date} onChange={(e) => set('amount_credited_date', e.target.value)} /></label>
        <label className="field">Customer Onboarding Date<input type="date" value={f.customer_onboarding_date} onChange={(e) => set('customer_onboarding_date', e.target.value)} /></label>
        <label className="field" style={{ gridColumn: '1 / -1' }}>Remarks<textarea rows={2} value={f.remarks} onChange={(e) => set('remarks', e.target.value)} /></label>
      </div>
      </fieldset>
      <div className="form-grid" style={{ marginTop: 12 }}>
        {f.currency && f.currency !== 'INR' && <>
          <label className="field">Record-specific INR rate (optional)<input type="number" step="0.000001" min="0" value={f.fx_rate_override} onChange={(e) => set('fx_rate_override', e.target.value)} placeholder="Else uses configured rate" /></label>
          <label className="field">Rate date<input type="date" value={f.fx_rate_override_date} onChange={(e) => set('fx_rate_override_date', e.target.value)} /></label>
        </>}
      </div>
      <div className="notice" style={{ marginTop: 14 }}>Each opportunity counts once. When a Signed contract is paid, <b>edit this record</b> to Amount Credited — don't add a new one. League eligibility uses the Signed date (Signed) or the Credited date (Amount Credited) between 1 Nov and 20 Dec 2026.
        {f.currency !== 'INR' && <> Non-INR values need a configured exchange rate (Revenue → Exchange rates) or a record-specific rate; until then they're flagged “pending conversion”.</>}</div>
      {dups && (
        <div className="notice amber" style={{ marginTop: 10 }}>
          <b>Possible duplicate.</b> This customer + opportunity already exists:
          <ul style={{ margin: '6px 0' }}>{dups.map((d) => <li key={d.id}>{d.bd_name} · {d.contract_status} · {d.contract_value.toLocaleString('en-IN')}</li>)}</ul>
          Update the existing record instead, unless this really is a separate opportunity.
          <div style={{ marginTop: 8 }}><button className="btn sm" onClick={() => save(true)}>It's a separate opportunity — save anyway</button></div>
        </div>
      )}
      {errs.length > 0 && <div className="errors" style={{ marginTop: 10 }}>{errs.map((e) => <div key={e}>• {e}</div>)}</div>}
      <Datalist id="dl-domain2" options={meta?.domains ?? []} />
      <Datalist id="dl-country2" options={meta?.countries ?? []} />
      <Datalist id="dl-opp" options={meta?.opportunity_options ?? []} />
      <Datalist id="dl-cur" options={meta?.currencies ?? []} />
    </Modal>
  )
}
