import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Award, Crown } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { api, errorText } from '../api'
import { ActivityFeed, KpiCard, Movement, todayMessage } from '../components/board'
import { CumulativeLine, DailyBars } from '../components/charts'
import { Avatar, DailyPill, Empty, Loading, StateTag, StatusPill, TypePill } from '../components/ui'
import { useSnapshot } from '../hooks'
import { fmtDate, fmtDay, fmtINR, fmtLakh, ordinal } from '../lib/format'
import type { DailyBD, Demo, OverallRow, Revenue } from '../types'

export function BDIndex() {
  const { data: s } = useSnapshot()
  if (!s) return <Loading />
  return (
    <>
      <div className="page-head"><div><h1>BD Performance</h1><div className="sub">Pick a BD for their detailed league journey</div></div></div>
      <div className="today-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}>
        {s.overall.map((r) => {
          const d = s.daily.per_bd[r.bd_id]
          return (
            <Link key={r.bd_id} to={`/bd/${r.bd_id}`} className={`bd-card ${r.is_leader ? 'achieved' : ''}`} style={{ color: 'var(--text)', textDecoration: 'none' }}>
              <div className="top"><Avatar id={r.bd_id} name={r.bd_name} size={42} />
                <div><div className="name">{r.bd_name} {r.is_leader && <Crown size={14} color="var(--gold)" />}</div>{d?.today && <DailyPill status={d.today.status} />}</div>
                <div className="pos">#{r.rank}</div></div>
              <div className="facts" style={{ marginTop: 12 }}>
                <span>Qualified</span><b>{r.total}</b><span>F2F / Virtual</span><b>{r.f2f} / {r.virtual}</b>
                <span>Target rate</span><b>{r.achievement_rate == null ? '—' : `${r.achievement_rate}%`}</b><span>Pending</span><b className={r.current_pending ? 'amber' : ''}>{r.current_pending}</b>
                <span>Revenue</span><b>{fmtLakh(r.revenue_inr)}</b><span>Scheduled</span><b>{r.scheduled}</b>
              </div>
            </Link>
          )
        })}
      </div>
    </>
  )
}

interface BDResp {
  bd: { id: number; name: string }; league: { f2f_target: number }; standing: OverallRow | null; daily: DailyBD | null
  revenue: { total_inr: number; award_eligible: boolean; gap_to_threshold: number; gap_to_leader: number; rank: number } | null
  weekly: { label: string; start: string; end: string; state: string; total: number; rank: number | null }[]
  f2f_challenge: { f2f: number; scheduled_f2f: number; rank: number } | null
  badges: { key: string; label: string; earned: boolean }[]
  counts: { scheduled: number; completed: number; completed_unqualified: number; no_show: number; pipeline: number }
  poc: Demo[]; demos: Demo[]; revenue_records: Revenue[]; activity: any[]; total_bds: number
}

export default function BDPerformance() {
  const { id } = useParams()
  const q = useQuery({ queryKey: ['bd', id], queryFn: () => api.get<BDResp>(`/api/bd/${id}`), refetchInterval: 30_000 })
  if (q.error) return <div className="errors">{errorText(q.error)}</div>
  if (!q.data) return <Loading />
  const { bd, standing: st, daily: d, revenue: rv } = q.data
  const days = d?.days ?? []
  let cum = 0
  const cumulative = days.map((x) => ({ date: x.date, value: (cum += x.done) }))
  const closedDays = days.filter((x) => x.closed)
  return (
    <>
      <div className="page-head">
        <Link to="/bd" className="btn ghost sm"><ArrowLeft size={15} /> All BDs</Link>
      </div>
      <div className="hero theme-dark" style={{ padding: 22 }}>
        <div className="row wrap" style={{ gap: 18, position: 'relative' }}>
          <Avatar id={bd.id} name={bd.name} size={72} />
          <div>
            <div className="hero-title" style={{ fontSize: 40 }}>{bd.name}</div>
            <div className="row wrap" style={{ marginTop: 6, gap: 8 }}>
              {st && <span className="pill gold">{ordinal(st.rank)} of {q.data.total_bds} overall</span>}
              {st?.is_leader && <span className="pill gold"><Crown size={12} /> League leader</span>}
              {st && <span className="pill grey">Since yesterday <Movement m={st.movement} /></span>}
              {d?.today && <DailyPill status={d.today.status} />}
            </div>
            {d && <div className="muted" style={{ marginTop: 8, maxWidth: 640 }}>{todayMessage(d)}</div>}
          </div>
          <span className="spacer" />
          <div className="row wrap" style={{ gap: 6 }}>
            {q.data.badges.map((b) => <span key={b.key} className={`pill ${b.earned ? 'gold' : 'grey'}`} style={{ opacity: b.earned ? 1 : 0.45 }} title={b.earned ? 'Earned' : 'Not yet'}><Award size={12} /> {b.label}</span>)}
          </div>
        </div>
      </div>

      <div className="section-label">Season stats</div>
      <div className="kpis">
        <KpiCard label="Qualified completed" value={st?.total ?? 0} accent="var(--gold)" />
        <KpiCard label="Qualified Virtual" value={st?.virtual ?? 0} accent="var(--blue)" />
        <KpiCard label="Qualified F2F" value={st?.f2f ?? 0} accent="var(--fire)" foot={q.data.f2f_challenge ? `${q.data.f2f_challenge.f2f} toward the ${q.data.league.f2f_target} · ${q.data.f2f_challenge.scheduled_f2f} scheduled` : undefined} />
        <KpiCard label="Scheduled demos" value={q.data.counts.scheduled} accent="var(--blue)" foot={`${q.data.counts.completed_unqualified} completed but not qualified`} />
        <KpiCard label="Target achievement" value={d?.achievement_rate ?? 0} accent="var(--green)" format={(v) => (d?.achievement_rate == null ? '—' : `${v.toFixed(0)}%`)}
          foot={`${d?.targets_achieved ?? 0} achieved · ${d?.targets_missed ?? 0} missed · ${d?.targets_assigned ?? 0} working days`} />
        <KpiCard label="Pending carry-forward" value={d?.current_pending ?? 0} accent={d?.current_pending ? 'var(--amber)' : 'var(--green)'}
          foot={d?.next_required ? `Next target: ${d.next_required}${d.next_target_date ? ` · ${fmtDay(d.next_target_date)}` : ''}` : 'No further league days'} />
        <KpiCard label="Streak" value={d?.current_streak ?? 0} accent="var(--gold)" foot={`Best: ${d?.best_streak ?? 0} days`} />
        <KpiCard label="Confirmed revenue" value={rv?.total_inr ?? 0} accent="var(--green)" format={fmtLakh}
          foot={rv?.award_eligible ? 'Eligible for Revenue Champion' : `${fmtLakh(rv?.gap_to_threshold ?? 0)} to ₹10L eligibility`} />
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(420px, 100%), 1fr))', marginTop: 16 }}>
        <div className="card"><div className="card-head"><h3>Qualified demos per working day</h3></div><DailyBars data={days.map((x) => ({ date: x.date, value: x.done }))} /></div>
        <div className="card"><div className="card-head"><h3>Cumulative qualified demos</h3></div><CumulativeLine data={cumulative} /></div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(420px, 100%), 1fr))', marginTop: 16 }}>
        <div className="card">
          <div className="card-head"><h3>Daily target history</h3><span className="hint">{closedDays.length} closed day(s)</span></div>
          {!days.length ? <Empty>No league working days yet.</Empty> : (
            <div className="table-wrap" style={{ maxHeight: 360 }}><table className="data">
              <thead><tr><th>Day</th><th className="num">Required</th><th className="num">Done</th><th className="num">Carry-out</th><th>Status</th></tr></thead>
              <tbody>{[...days].reverse().map((x) => (
                <tr key={x.date}><td className="nowrap">{fmtDay(x.date)}</td><td className="num">{x.required}</td><td className="num">{x.done}</td>
                  <td className="num">{x.closed ? x.pending_after : <span className="dim">open</span>}</td><td><DailyPill status={x.status} /></td></tr>))}</tbody>
            </table></div>)}
        </div>
        <div className="card">
          <div className="card-head"><h3>Weekly performance</h3></div>
          <div className="table-wrap"><table className="data">
            <thead><tr><th>Week</th><th className="num">Qualified</th><th className="num">Rank</th><th>State</th></tr></thead>
            <tbody>{q.data.weekly.map((w) => (
              <tr key={w.start} className={w.state === 'upcoming' ? 'muted-row' : ''}><td>{w.label}</td><td className="num">{w.total}</td><td className="num">{w.state === 'upcoming' ? '—' : w.rank}</td><td><StateTag state={w.state} /></td></tr>))}</tbody>
          </table></div>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(420px, 100%), 1fr))', marginTop: 16 }}>
        <div className="card">
          <div className="card-head"><h3>POC progress</h3></div>
          {!q.data.poc.length ? <Empty>No POCs yet.</Empty> : (
            <div className="table-wrap"><table className="data"><thead><tr><th>Customer</th><th>Status</th><th>Started</th><th>Remarks</th></tr></thead>
              <tbody>{q.data.poc.map((p) => <tr key={p.id}><td>{p.customer_name}</td><td><StatusPill status={p.status} /></td><td>{fmtDate(p.poc_started_on)}</td><td className="small">{p.poc_remarks}</td></tr>)}</tbody></table></div>)}
          <div className="card-head" style={{ marginTop: 18 }}><h3>Revenue records</h3></div>
          {!q.data.revenue_records.length ? <Empty>No revenue recorded.</Empty> : (
            <div className="table-wrap"><table className="data"><thead><tr><th>Customer</th><th>Opportunity</th><th>Status</th><th className="num">INR</th></tr></thead>
              <tbody>{q.data.revenue_records.map((r) => <tr key={r.id} className={r.evaluation.eligible ? '' : 'muted-row'}><td>{r.customer_name}</td><td>{r.opportunity_name}</td><td>{r.contract_status}</td>
                <td className="num">{r.evaluation.inr_value != null ? fmtINR(r.evaluation.inr_value) : r.evaluation.reason}</td></tr>)}</tbody></table></div>)}
        </div>
        <div className="card"><div className="card-head"><h3>Recent activity</h3></div><ActivityFeed items={q.data.activity} limit={15} /></div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head"><h3>All demos</h3><span className="hint">{q.data.demos.length} records</span></div>
        <div className="table-wrap" style={{ maxHeight: 420 }}><table className="data">
          <thead><tr><th>Date</th><th>Customer</th><th>Country</th><th>Type</th><th>Status</th><th>Qualified</th><th>Counts</th></tr></thead>
          <tbody>{q.data.demos.map((x) => (
            <tr key={x.id}><td className="nowrap">{fmtDate(x.demo_date)}</td><td>{x.customer_name}</td><td className="small">{x.country ?? x.city}</td><td><TypePill type={x.effective_type ?? x.demo_type} /></td>
              <td><StatusPill status={x.status} /></td><td>{x.qualified ?? '—'}</td><td>{x.counts ? <span className="pill green">Yes</span> : ''}</td></tr>))}</tbody>
        </table></div>
      </div>
    </>
  )
}
