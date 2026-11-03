import { Crown, Lock, TrendingUp, Unlock } from 'lucide-react'
import { api, errorText } from '../api'
import { ActivityFeed, AwardsGrid, F2FChallenge, F2FMeetingsLeaderboard, Hero, KpiRow, Motivation, OverallLeaderboard, RevenueBoard, RevenueLeaderboardTable, TodayBoard } from '../components/board'
import { useCelebrations } from '../components/celebrate'
import { SyncBadge } from '../components/sync'
import { Loading, useConfirm, useToast } from '../components/ui'
import { useRefreshAll, useSnapshot } from '../hooks'
import { fmtDay, joinNames } from '../lib/format'

export default function Dashboard() {
  const { data: s, error } = useSnapshot()
  const { hl, layer } = useCelebrations(s, 'dashboard')
  const confirm = useConfirm()
  const toast = useToast()
  const refresh = useRefreshAll()
  if (error) return <div className="errors">{errorText(error)}</div>
  if (!s) return <Loading />

  const d = s.daily
  const canClose = d.is_working_day && d.within_league && !d.today_closed
  const closeDay = async () => {
    if (!(await confirm({ title: `Close ${fmtDay(d.today)}?`, confirm: 'Close day',
      body: <>This finalises today's daily targets for all BDs now, instead of waiting for the {d.cutoff} cutoff. BDs below their required target are marked <b>Target Missed</b> and the shortfall carries forward. You can reopen until the cutoff.</> }))) return
    try {
      await api.post(`/api/days/${d.today}/close`)
      refresh()
    } catch (e) { toast({ tone: 'red', title: 'Could not close day', body: errorText(e) }) }
  }
  const reopen = async () => {
    try { await api.post(`/api/days/${d.today}/reopen`); refresh() } catch (e) { toast({ tone: 'red', title: 'Could not reopen', body: errorText(e) }) }
  }
  const leader = s.overall.filter((r) => r.is_leader)
  const lowest = s.overall.filter((r) => r.is_lowest && s.overall.some((x) => x.total > 0))

  return (
    <>
      {layer}
      <Hero league={s.league} bdCount={s.kpis.bd_count} />
      <div style={{ marginTop: 14 }}><SyncBadge /></div>
      <div className="card" style={{ marginTop: 14, padding: '12px 18px' }}>
        <Motivation messages={s.league.motivational_messages} />
      </div>

      <div className="section-label">League pulse</div>
      <KpiRow k={s.kpis} f2f={s.f2f} />

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(240px, 100%), 1fr))', marginTop: 14 }}>
        <LeadCard lead={leader.length > 0} label="Leading the league"
          value={leader.length ? leader.map((l) => l.bd_name).join(' & ') : '—'}
          sub={leader[0] ? `${leader[0].total} qualified completed demos` : 'First qualified demo takes the crown'} />
        <LeadCard lead={false} label="Comeback zone"
          value={lowest.length ? joinNames(lowest.map((l) => l.bd_name)) : '—'}
          sub={lowest.length ? 'Every qualified demo closes the gap — the race is long.' : 'Everyone is level.'} />
        <LeadCard lead={s.f2f.leaders.length > 0} label="F2F challenge leader"
          value={s.f2f.leaders.length ? s.f2f.leaders.map((l) => l.bd_name).join(' & ') : '—'}
          sub={`${s.f2f.achieved}/${s.f2f.target} qualified F2F`} />
        <LeadCard lead={!!s.revenue.per_bd[0]?.total_inr} label="Revenue leader"
          value={s.revenue.per_bd[0]?.total_inr ? s.revenue.per_bd.filter((r) => r.rank === 1).map((r) => r.bd_name).join(' & ') : '—'}
          sub={s.revenue.champions.length ? `Champion (≥ ₹10L): ${s.revenue.champions.map((c) => c.bd_name).join(' & ')}` : 'No BD at ₹10 lakh yet'} />
      </div>

      <div className="section-label">Today's BD performance board</div>
      <div className="card">
        <div className="card-head">
          <h2 style={{ color: 'var(--brand)' }}>{d.is_working_day ? `TODAY - ${fmtDay(d.today)}` : `${fmtDay(d.today)} · Weekly holiday`}</h2>
          {d.is_working_day && d.within_league && (d.today_closed
            ? <span className="pill grey"><Lock size={12} /> Day closed — results final</span>
            : <span className="pill blue"><span className="live-dot" /> In progress · auto-closes {d.cutoff}</span>)}
          <span className="spacer" />
          {canClose && <button className="btn sm" onClick={closeDay}><Lock size={14} /> Close day now</button>}
          {d.manually_closed_today && <button className="btn sm ghost" onClick={reopen}><Unlock size={14} /> Reopen</button>}
        </div>
        <TodayBoard snap={s} hl={hl} />
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head"><h2 style={{ color: 'var(--brand)' }}>Overall League Leaderboard</h2><span className="tag-provisional">Official · live</span>
          <span className="hint">Qualified completed demos · F2F + Virtual · arrows = movement since yesterday</span></div>
        <OverallLeaderboard rows={s.overall} hl={hl} />
      </div>

      <div className="section-label">F2F 45-demo challenge</div>
      <div className="card feature theme-dark"><F2FChallenge f2f={s.f2f} hl={hl} /></div>
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head"><h2 style={{ color: 'var(--brand)' }}>F2F Meetings Leaderboard</h2><span className="tag-provisional">Official · live</span>
          <span className="hint">Qualified completed F2F · Malaysia, Singapore, Middle East · scheduled pipeline</span></div>
        <F2FMeetingsLeaderboard rows={s.f2f.leaderboard} hl={hl} />
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head"><h2 style={{ color: 'var(--brand)', display: 'inline-flex', alignItems: 'center', gap: 8 }}><TrendingUp size={20} /> Revenue Leaderboard</h2></div>
        <RevenueBoard rev={s.revenue} hl={hl} />
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head"><h2 style={{ color: 'var(--brand)', display: 'inline-flex', alignItems: 'center', gap: 8 }}><TrendingUp size={20} /> Revenue Standings</h2>
          <span className="tag-provisional">Official · live</span>
          <span className="hint">Confirmed league revenue · ≥ ₹10L to qualify for Revenue Champion</span></div>
        <RevenueLeaderboardTable rows={s.revenue.per_bd} threshold={s.revenue.threshold_inr} hl={hl} />
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head"><h2 style={{ color: 'var(--brand)' }}>Awards & Weekly Standings</h2></div>
        <AwardsGrid awards={s.awards} revenue={s.revenue} />
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head"><h2 style={{ color: 'var(--brand)' }}>Recent Activity</h2></div>
        <ActivityFeed items={s.activity} limit={14} />
      </div>
    </>
  )
}

function LeadCard({ lead, label, value, sub }: { lead: boolean; label: string; value: string; sub: string }) {
  return (
    <div className={`card tight lead-card shine ${lead ? 'is-lead' : 'not-lead'}`}>
      {lead && <Crown size={26} className="lead-crown" />}
      <div className="tiny upper muted">{label}</div>
      <div className="num lead-val" style={{ fontSize: 28 }}>{value}</div>
      <div className="small muted">{sub}</div>
    </div>
  )
}
