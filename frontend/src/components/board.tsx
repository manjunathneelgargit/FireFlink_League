import { AnimatePresence, LayoutGroup, motion } from 'framer-motion'
import {
  Activity as ActIcon, AlertTriangle, ArrowDown, ArrowUp, CalendarCheck, CheckCircle2, Crown, Flame, Globe2, IndianRupee,
  Medal, Plane, Sparkles, Target, Trophy, TrendingUp, Upload, Users,
} from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { fmtDate, fmtDay, fmtINR, fmtLakh, timeAgo } from '../lib/format'
import type { Activity, Awards, DailyBD, F2F, F2FRow, Kpis, League, OverallRow, RevenueBD, RevenueSummary, Snapshot } from '../types'
import type { Highlights } from './celebrate'
import { AnimatedCheck, AnimatedNumber, Avatar, DailyPill, Ring, StateTag } from './ui'

/* ------------------------------------------------------------------ hero */
export function Countdown({ endAt, phase }: { endAt: string; phase: League['phase'] }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  const ms = Math.max(0, new Date(endAt).getTime() - now)
  if (phase === 'after' || ms === 0) return <div className="pill gold" style={{ fontSize: 14, padding: '8px 14px' }}><Trophy size={16} /> League complete</div>
  const d = Math.floor(ms / 864e5), h = Math.floor((ms % 864e5) / 36e5), m = Math.floor((ms % 36e5) / 6e4), s = Math.floor((ms % 6e4) / 1e3)
  const cell = (v: number, l: string) => (
    <div className="cell"><div className="v">{String(v).padStart(2, '0')}</div><div className="l">{l}</div></div>
  )
  return <div className="countdown" aria-label="Countdown to league completion">{cell(d, 'Days')}{cell(h, 'Hrs')}{cell(m, 'Min')}{cell(s, 'Sec')}</div>
}

export function Hero({ league, bdCount }: { league: League; bdCount: number }) {
  return (
    <div className="hero theme-dark">
      <div className="row wrap" style={{ alignItems: 'flex-start', gap: 20, position: 'relative' }}>
        <div style={{ flex: '1 1 380px' }}>
          <span className="eyebrow">
            {league.phase === 'live' && <><span className="live-dot" /> Live league · Sales championship</>}
            {league.phase === 'before' && 'Starting soon'}
            {league.phase === 'after' && 'League complete'}
          </span>
          <div className="hero-title" style={{ marginTop: 12 }}><span className="fire">FireFlink 4.0</span> – Go Beyond</div>
          <div className="hero-tag">Ee Sala Market Namde!</div>
          <div className="hero-meta">
            <span><CalendarCheck size={14} style={{ verticalAlign: -2 }} /> <b>{fmtDate(league.start)} – {fmtDate(league.end)}</b></span>
            <span><Users size={14} style={{ verticalAlign: -2 }} /> <b>{bdCount}</b> BDs competing</span>
            <span><Plane size={14} style={{ verticalAlign: -2 }} /> F2F challenge <b>{league.f2f_target}</b></span>
            <span><Target size={14} style={{ verticalAlign: -2 }} /> <b>{league.working_days_left}</b> of {league.working_days_total} working days left</span>
            <span>Login <b>{league.office_login}</b> · Stand-up <b>{league.standup}</b></span>
          </div>
        </div>
        <div className="col" style={{ alignItems: 'flex-end' }}>
          <div className="tiny upper muted" style={{ fontWeight: 600 }}>Countdown to final whistle</div>
          <Countdown endAt={league.end_at} phase={league.phase} />
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ KPIs */
export function KpiCard({ label, value, foot, icon, accent, format }: {
  label: string; value: number; foot?: ReactNode; icon?: ReactNode; accent?: string; format?: (v: number) => string
}) {
  return (
    <div className="kpi" style={{ ['--accent' as any]: accent }}>
      <div className="label">{icon}{label}</div>
      <div className="value" style={{ color: accent }}><AnimatedNumber value={value} format={format} /></div>
      {foot && <div className="foot">{foot}</div>}
    </div>
  )
}

export function KpiRow({ k, f2f }: { k: Kpis; f2f: F2F }) {
  return (
    <div className="kpis">
      <KpiCard label="Qualified demos" value={k.qualified_completed} accent="var(--gold)" icon={<Trophy size={13} />}
        foot={<>{k.qualified_f2f} F2F · {k.qualified_virtual} Virtual</>} />
      <KpiCard label="Scheduled demos" value={k.scheduled} accent="var(--blue)" icon={<CalendarCheck size={13} />}
        foot={<>{k.scheduled_f2f} F2F · {k.scheduled_virtual} Virtual</>} />
      <KpiCard label="Daily target hit" value={k.target_achievement_rate ?? 0} accent="var(--green)" icon={<Target size={13} />}
        format={(v) => (k.target_achievement_rate == null ? '—' : `${v.toFixed(0)}%`)}
        foot={<>{k.targets_achieved}/{k.targets_assigned} BD-days achieved</>} />
      <KpiCard label="Qualified F2F" value={k.qualified_f2f} accent="var(--fire)" icon={<Plane size={13} />}
        foot={<>{f2f.achieved} count toward the 45</>} />
      <KpiCard label="F2F challenge" value={f2f.percent} accent="var(--gold)" icon={<Flame size={13} />}
        format={(v) => `${v.toFixed(v < 10 && v > 0 ? 1 : 0)}%`} foot={<>{f2f.achieved} / {f2f.target} · {f2f.remaining} to go</>} />
      <KpiCard label="Confirmed revenue" value={k.total_revenue_inr} accent="var(--green)" icon={<IndianRupee size={13} />}
        format={fmtLakh} foot={<>league-period, INR</>} />
      <KpiCard label="On target today" value={k.on_target_today} accent="var(--green)" icon={<CheckCircle2 size={13} />}
        format={(v) => `${Math.round(v)}/${k.bd_count}`} foot={<>{k.outstanding_carry_forward} pending carry-forward</>} />
    </div>
  )
}

/* ------------------------------------------------------------------ today */
const DURING_DAY = "The day isn't over yet. One qualified demo can change your position. Make it happen!"
const AFTER_MISS = "Today didn't go as planned. Tomorrow is your opportunity to bounce back. Clear your pending target and get back in the race!"

export function todayMessage(b: DailyBD): string {
  const t = b.today
  if (!t) return b.next_required ? `Next working day target: ${b.next_required}` : 'League complete.'
  if (t.status === 'Target Achieved') return 'Target Achieved! Great work. Keep the momentum going.'
  if (t.status === 'Target Missed') return AFTER_MISS
  if (t.status === 'Not Started') return 'Office login at 8:30 — a fresh day, a fresh shot at the top.'
  return DURING_DAY
}

export function TodayBoard({ snap, hl }: { snap: Snapshot; hl: Highlights }) {
  const { daily, overall } = snap
  const rank = Object.fromEntries(overall.map((r) => [r.bd_id, r]))
  const list = Object.values(daily.per_bd).sort((a, b) => (rank[a.bd_id]?.rank ?? 99) - (rank[b.bd_id]?.rank ?? 99) || a.bd_name.localeCompare(b.bd_name))
  if (!daily.is_working_day || !daily.within_league) {
    const msg = !daily.within_league ? (snap.league.phase === 'after' ? 'The league is complete — see final standings below.' : 'The league has not started yet.')
      : 'Sunday — weekly holiday. Pending targets carry into the next working day.'
    return (
      <div className="col">
        <div className="notice">{msg}</div>
        <div className="today-grid">
          {list.map((b) => (
            <div key={b.bd_id} className={`bd-card ${b.current_pending ? 'pending' : ''}`}>
              <div className="top"><Avatar id={b.bd_id} name={b.bd_name} /><div className="name">{b.bd_name}</div></div>
              <div className="facts" style={{ marginTop: 10 }}>
                <span>Next target</span><b>{b.next_required ?? '—'}{b.next_target_date ? <span className="small muted"> · {fmtDay(b.next_target_date)}</span> : ''}</b>
                <span>Pending</span><b className={b.current_pending ? 'amber' : ''}>{b.current_pending}</b>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }
  return (
    <div className="today-grid">
      {list.map((b) => {
        const t = b.today!
        const ok = t.status === 'Target Achieved'
        const missed = t.status === 'Target Missed'
        const cls = ok ? 'achieved' : missed ? 'missed' : t.pending_before > 0 ? 'pending' : ''
        const anim = hl.glow.has(b.bd_id) ? 'anim-glow' : hl.pulse.has(b.bd_id) ? 'anim-pulse' : ''
        const r = rank[b.bd_id]
        return (
          <motion.div layout key={b.bd_id} className={`bd-card ${cls} ${anim}`}>
            <div className="top">
              <Avatar id={b.bd_id} name={b.bd_name} />
              <div style={{ minWidth: 0 }}>
                <Link to={`/bd/${b.bd_id}`} className="name" style={{ color: 'var(--text)' }}>{b.bd_name}</Link>
                <div style={{ marginTop: 3 }}><DailyPill status={t.status} /></div>
              </div>
              <div className="pos" title="Overall league rank">#{r?.rank ?? '—'}</div>
            </div>
            <div className="meter">
              <Ring value={t.done} max={t.required} size={56} stroke={6} color={ok ? 'var(--green)' : missed ? 'var(--red)' : 'var(--amber)'}>
                {ok ? <AnimatedCheck size={22} /> : missed ? <AlertTriangle size={18} color="var(--red)" className={hl.pulse.has(b.bd_id) ? 'anim-shake' : ''} />
                  : <span className="num" style={{ fontSize: 15 }}>{t.done}/{t.required}</span>}
              </Ring>
              <div className="facts">
                <span>Done today</span><b>{t.done}</b>
                <span>Required</span><b>{t.required}</b>
                <span>Carry-in</span><b className={t.pending_before ? 'amber' : ''}>{t.pending_before}</b>
                <span>{t.closed ? 'Carry-out' : 'Still needed'}</span>
                <b className={missed ? 'red' : ''}>{t.closed ? (t.pending_after ?? 0) : Math.max(0, t.required - t.done)}</b>
              </div>
            </div>
            <div className="msg">
              {todayMessage(b)}
              {missed && b.next_required != null && <div className="amber" style={{ fontWeight: 700, marginTop: 4 }}>Next working day target: {b.next_required}</div>}
            </div>
          </motion.div>
        )
      })}
    </div>
  )
}

/* ------------------------------------------------------------------ overall leaderboard */
export function Movement({ m }: { m: number }) {
  if (!m) return <span className="move dim">–</span>
  return m > 0 ? <span className="move up"><ArrowUp size={12} />{m}</span> : <span className="move down"><ArrowDown size={12} />{-m}</span>
}

export function OverallLeaderboard({ rows, hl, compact }: { rows: OverallRow[]; hl: Highlights; compact?: boolean }) {
  const anyScore = rows.some((r) => r.total > 0)
  return (
    <LayoutGroup>
      <div className="lb" style={{ ['--cols' as any]: compact ? 3 : 5 }}>
        <AnimatePresence initial={false}>
          {rows.map((r) => {
            const moved = hl.moved.get(r.bd_id)
            return (
              <motion.div layout="position" key={r.bd_id} transition={{ type: 'spring', stiffness: 260, damping: 28 }}
                className={`lb-row ${r.is_leader ? 'leader shine' : ''} ${r.is_lowest && anyScore ? 'lowest' : ''} ${hl.gold.has(r.bd_id) ? 'anim-gold' : ''}`}>
                <div className="lb-rank" style={{ position: 'relative' }}>
                  {r.is_leader && <Crown size={22} className="crown" />}
                  {r.rank}
                </div>
                <div className="lb-name">
                  <Avatar id={r.bd_id} name={r.bd_name} />
                  <div style={{ minWidth: 0 }}>
                    <Link to={`/bd/${r.bd_id}`} className="n" style={{ color: 'var(--text)', display: 'block' }}>{r.bd_name}</Link>
                    <div className="row wrap tiny" style={{ gap: '2px 6px' }}>
                      <span title="Movement since end of previous day"><Movement m={r.movement} /></span>
                      {moved && <motion.span initial={{ y: moved === 'up' ? 6 : -6, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className={`move ${moved}`}>{moved === 'up' ? '▲ moving up' : '▼'}</motion.span>}
                      {r.is_leader && <span className="gold" style={{ fontWeight: 700 }}>Leader</span>}
                      {r.is_lowest && anyScore && <span className="amber" title="One qualified demo can change it">Comeback zone</span>}
                      {r.current_pending > 0 && <span className="amber">{r.current_pending} pending</span>}
                    </div>
                  </div>
                </div>
                <div className="lb-stat big"><div className="v"><AnimatedNumber value={r.total} /></div><div className="l">Qualified</div></div>
                <div className="lb-stat"><div className="v" style={{ color: 'var(--fire)' }}>{r.f2f}</div><div className="l">F2F</div></div>
                <div className="lb-stat"><div className="v" style={{ color: 'var(--blue)' }}>{r.virtual}</div><div className="l">Virtual</div></div>
                {!compact && <div className="lb-stat"><div className="v">{r.achievement_rate == null ? '—' : `${r.achievement_rate.toFixed(0)}%`}</div><div className="l">Target rate</div></div>}
                {!compact && <div className="lb-stat"><div className="v" style={{ fontSize: 20 }}>{fmtLakh(r.revenue_inr)}</div><div className="l">Revenue</div></div>}
              </motion.div>
            )
          })}
        </AnimatePresence>
        {!anyScore && <div className="small muted" style={{ padding: '4px 4px' }}>No qualified completed demos yet — the first one takes the crown.</div>}
      </div>
    </LayoutGroup>
  )
}

/* ------------------------------------------------------------------ F2F meetings leaderboard */
export function F2FMeetingsLeaderboard({ rows, hl }: { rows: F2FRow[]; hl: Highlights }) {
  const anyCompleted = rows.some((r) => r.f2f > 0)
  const anyScore = rows.some((r) => r.f2f > 0 || r.scheduled_f2f > 0)
  // Rank by completed F2F when any exist; otherwise by scheduled pipeline.
  const metric = (r: F2FRow) => (anyCompleted ? r.f2f : r.scheduled_f2f)
  const ranked = [...rows]
    .sort((a, b) => metric(b) - metric(a) || a.bd_name.localeCompare(b.bd_name))
    .map((r, _, all) => ({
      ...r,
      displayRank: 1 + all.filter((o) => metric(o) > metric(r)).length,
    }))
  const topCompleted = Math.max(0, ...ranked.map((r) => r.f2f))
  return (
    <LayoutGroup>
      <div className="lb" style={{ ['--cols' as any]: 3 }}>
        <AnimatePresence initial={false}>
          {ranked.map((r) => {
            // Crown / shine only for completed-F2F leaders — never for scheduled-only ranking.
            const isLeader = topCompleted > 0 && r.f2f === topCompleted
            return (
              <motion.div layout="position" key={r.bd_id} transition={{ type: 'spring', stiffness: 260, damping: 28 }}
                className={`lb-row ${isLeader ? 'leader shine' : ''} ${hl.gold.has(r.bd_id) ? 'anim-gold' : ''}`}>
                <div className="lb-rank" style={{ position: 'relative' }}>
                  {isLeader && <Crown size={22} className="crown" />}
                  {r.displayRank}
                </div>
                <div className="lb-name">
                  <Avatar id={r.bd_id} name={r.bd_name} />
                  <div style={{ minWidth: 0 }}>
                    <Link to={`/bd/${r.bd_id}`} className="n" style={{ color: 'var(--text)', display: 'block' }}>{r.bd_name}</Link>
                    {isLeader && <div className="tiny gold" style={{ fontWeight: 700 }}>Leader</div>}
                  </div>
                </div>
                <div className="lb-stat big"><div className="v" style={{ color: 'var(--fire)' }}><AnimatedNumber value={r.f2f} /></div><div className="l">Completed</div></div>
                <div className="lb-stat"><div className="v" style={{ color: 'var(--blue)' }}>{r.scheduled_f2f}</div><div className="l">Scheduled</div></div>
                <div className="lb-stat"><div className="v"><AnimatedNumber value={r.f2f + r.scheduled_f2f} /></div><div className="l">Total</div></div>
              </motion.div>
            )
          })}
        </AnimatePresence>
        {!anyScore && <div className="small muted" style={{ padding: '4px 4px' }}>No F2F meetings yet — scheduled and completed demos will appear here.</div>}
      </div>
    </LayoutGroup>
  )
}

/* ------------------------------------------------------------------ revenue leaderboard table */
export function RevenueLeaderboardTable({ rows, threshold, hl }: { rows: RevenueBD[]; threshold: number; hl: Highlights }) {
  const anyScore = rows.some((r) => r.total_inr > 0)
  const topTotal = Math.max(0, ...rows.map((r) => r.total_inr))
  return (
    <LayoutGroup>
      <div className="lb" style={{ ['--cols' as any]: 4 }}>
        <AnimatePresence initial={false}>
          {rows.map((r) => {
            const isLeader = topTotal > 0 && r.rank === 1 && r.total_inr === topTotal
            return (
              <motion.div layout="position" key={r.bd_id} transition={{ type: 'spring', stiffness: 260, damping: 28 }}
                className={`lb-row ${isLeader ? 'leader shine' : ''} ${hl.gold.has(r.bd_id) ? 'anim-gold' : ''}`}>
                <div className="lb-rank" style={{ position: 'relative' }}>
                  {isLeader && <Crown size={22} className="crown" />}
                  {r.rank}
                </div>
                <div className="lb-name">
                  <Avatar id={r.bd_id} name={r.bd_name} />
                  <div style={{ minWidth: 0 }}>
                    <Link to={`/bd/${r.bd_id}`} className="n" style={{ color: 'var(--text)', display: 'block' }}>{r.bd_name}</Link>
                    <div className="row wrap tiny" style={{ gap: '2px 6px' }}>
                      {isLeader && <span className="gold" style={{ fontWeight: 700 }}>Leader</span>}
                      {r.award_eligible ? <span className="pill green" style={{ fontSize: 10 }}>Eligible</span>
                        : <span className="amber">{fmtLakh(r.gap_to_threshold)} to ₹10L</span>}
                    </div>
                  </div>
                </div>
                <div className="lb-stat big"><div className="v"><AnimatedNumber value={r.total_inr} format={fmtLakh} /></div><div className="l">Total</div></div>
                <div className="lb-stat"><div className="v">{fmtLakh(r.signed_inr)}</div><div className="l">Signed</div></div>
                <div className="lb-stat"><div className="v">{fmtLakh(r.credited_inr)}</div><div className="l">Credited</div></div>
                <div className="lb-stat"><div className="v">{r.gap_to_leader > 0 ? `−${fmtLakh(r.gap_to_leader)}` : r.total_inr > 0 ? '—' : '—'}</div><div className="l">Gap</div></div>
              </motion.div>
            )
          })}
        </AnimatePresence>
        {!anyScore && <div className="small muted" style={{ padding: '4px 4px' }}>No confirmed revenue yet — first ₹ toward {fmtLakh(threshold)} starts the race.</div>}
      </div>
    </LayoutGroup>
  )
}

/* ------------------------------------------------------------------ F2F */
export function F2FChallenge({ f2f, hl, size = 220 }: { f2f: F2F; hl: Highlights; size?: number }) {
  const maxBd = Math.max(1, ...f2f.leaderboard.map((r) => r.f2f))
  const scheduled = f2f.scheduled_pipeline.total
  const scheduledPct = f2f.target ? Math.round(Math.min(100, (100 * scheduled) / f2f.target) * 10) / 10 : 0
  return (
    <div className={`f2f-wrap ${hl.f2fMilestone ? 'anim-gold' : ''}`} style={{ borderRadius: 16 }}>
      <div className="f2f-rings">
        <div className="f2f-ring-block">
          <Ring value={scheduled} max={f2f.target} size={size} stroke={16} color="url(#f2fsched)">
            <div style={{ textAlign: 'center' }}>
              <div className="num" style={{ fontSize: size * 0.27, lineHeight: 1, color: 'var(--blue)' }}><AnimatedNumber value={scheduled} /></div>
              <div className="muted small">of {f2f.target} scheduled F2F</div>
              <div className="num" style={{ fontSize: 22, color: 'var(--blue)' }}>{scheduledPct}%</div>
            </div>
          </Ring>
          <div className="f2f-ring-stats">
            <div>Scheduled: <b className="num" style={{ color: 'var(--blue)' }}>{scheduled}</b></div>
            <div>Remaining: <b className="num amber">{Math.max(0, f2f.target - scheduled)}</b></div>
          </div>
        </div>
        <div className="f2f-ring-block">
          <Ring value={f2f.achieved} max={f2f.target} size={size} stroke={16} color="url(#f2fgrad)">
            <div style={{ textAlign: 'center' }}>
              {hl.f2fMilestone && <motion.div initial={{ scale: 0, rotate: -30 }} animate={{ scale: 1, rotate: 0 }} transition={{ type: 'spring' }}><Trophy color="var(--gold)" size={30} /></motion.div>}
              <div className="num" style={{ fontSize: size * 0.27, lineHeight: 1 }}><AnimatedNumber value={f2f.achieved} /></div>
              <div className="muted small">of {f2f.target} qualified F2F</div>
              <div className="gold num" style={{ fontSize: 22 }}>{f2f.percent}%</div>
            </div>
          </Ring>
          <div className="f2f-ring-stats">
            <div>Scheduled: <b className="num" style={{ color: 'var(--blue)' }}>{scheduled}</b></div>
            <div>Completed: <b className="num">{f2f.achieved}</b></div>
          </div>
        </div>
        <svg width="0" height="0"><defs>
          <linearGradient id="f2fgrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#c79fd0" /><stop offset="1" stopColor="#ff6be1" /></linearGradient>
          <linearGradient id="f2fsched" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#6b8cff" /><stop offset="1" stopColor="#8f84ff" /></linearGradient>
        </defs></svg>
      </div>
      <div className="col" style={{ gap: 14, width: '100%' }}>
        <div className="f2f-split">
          <div className="col f2f-region" style={{ gap: 7 }}>
            <div className="tiny upper muted" style={{ fontWeight: 700 }}>By region</div>
            <div className="hbar hbar-head">
              <span className="tiny upper muted">Country</span>
              <span />
              <span className="tiny upper muted" style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>Sched + Done</span>
            </div>
            {Object.entries(f2f.per_region).map(([r, v]) => {
              const sched = f2f.scheduled_pipeline.by_region[r] ?? 0
              return (
                <div key={r} className="hbar"><span className="small"><Globe2 size={12} style={{ verticalAlign: -1 }} /> {r}</span>
                  <div className="bar"><i style={{ width: `${f2f.achieved ? (100 * v) / Math.max(1, f2f.achieved) : 0}%` }} /></div>
                  <span className="num" style={{ textAlign: 'right' }}>{sched}<span className="dim small"> +{v}</span></span></div>
              )
            })}
          </div>
          <div className="col f2f-bd" style={{ gap: 7 }}>
            <div className="tiny upper muted" style={{ fontWeight: 700 }}>BD contributions {f2f.leaders.length > 1 && <span className="pill amber" style={{ marginLeft: 6 }}>Tie – admin review</span>}</div>
            <div className="hbar hbar-head">
              <span className="tiny upper muted">BD</span>
              <span />
              <span className="tiny upper muted" style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>Sched + Done</span>
            </div>
            {f2f.leaderboard.map((r) => (
              <div key={r.bd_id} className="hbar"><span className="small" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.f2f > 0 && r.rank === 1 ? '👑 ' : ''}{r.bd_name}</span>
                <div className="bar"><i style={{ width: `${(100 * r.f2f) / maxBd}%` }} /></div>
                <span className="num" style={{ textAlign: 'right' }}>{r.scheduled_f2f ?? 0}<span className="dim small"> +{r.f2f}</span></span></div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ revenue */
export function RevenueBoard({ rev, hl }: { rev: RevenueSummary; hl: Highlights }) {
  const max = Math.max(rev.threshold_inr, ...rev.per_bd.map((r) => r.total_inr))
  const champIds = new Set(rev.champions.map((c) => c.bd_id))
  return (
    <div className={`col ${hl.revenueChanged ? 'anim-gold' : ''}`} style={{ gap: 10, borderRadius: 12 }}>
      <div className="row wrap" style={{ gap: 24 }}>
        <div><div className="tiny upper muted">Total confirmed league revenue</div><div className="num green" style={{ fontSize: 38 }}><AnimatedNumber value={rev.total_inr} format={fmtINR} /></div></div>
        <div><div className="tiny upper muted">Revenue Champion</div>
          <div className="num gold" style={{ fontSize: 28 }}>{rev.champions.length ? rev.champions.map((c) => c.bd_name).join(' & ') : '—'}</div>
          <div className="tiny muted">{rev.champions.length ? (rev.tie ? `Tie — ₹1,00,000 split: ${fmtINR(rev.champions[0].prize_share_inr)} each` : 'Provisional') : `Needs ≥ ${fmtLakh(rev.threshold_inr)} to qualify`}</div></div>
        {rev.pending_conversion_count > 0 && <div className="pill amber">{rev.pending_conversion_count} record(s) pending currency conversion</div>}
      </div>
      <div className="col" style={{ gap: 8 }}>
        {rev.per_bd.map((r) => (
          <div key={r.bd_id} className="row" style={{ gap: 10 }}>
            <span className="num dim" style={{ width: 22, textAlign: 'right' }}>{r.rank}</span>
            <span style={{ width: 120, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{champIds.has(r.bd_id) ? '👑 ' : ''}{r.bd_name}</span>
            <div className="bar green" style={{ flex: 1, position: 'relative' }}>
              <i style={{ width: `${(100 * r.total_inr) / max}%` }} />
              <span title="₹10 lakh threshold" style={{ position: 'absolute', top: -3, bottom: -3, left: `${(100 * rev.threshold_inr) / max}%`, width: 2, background: 'var(--gold)' }} />
            </div>
            <span className="num" style={{ width: 92, textAlign: 'right' }}>{fmtLakh(r.total_inr)}</span>
            <span style={{ width: 110 }}>{r.award_eligible ? <span className="pill green">Eligible</span> : <span className="pill grey" title="Gap to ₹10 lakh">{fmtLakh(r.gap_to_threshold)} to go</span>}</span>
            <span className="small muted nowrap" style={{ width: 100, textAlign: 'right' }}>{r.gap_to_leader > 0 ? `−${fmtLakh(r.gap_to_leader)}` : r.total_inr > 0 ? 'Leader' : ''}</span>
          </div>
        ))}
      </div>
      <div className="tiny dim">Gold line = ₹10 lakh award-eligibility threshold. All confirmed revenue is shown, including amounts below the threshold.</div>
    </div>
  )
}

/* ------------------------------------------------------------------ awards */
function AwardCard({ title, prize, who, sub, state, icon, extra }: {
  title: string; prize: string | null; who: string; sub: ReactNode; state: string; icon: ReactNode; extra?: ReactNode
}) {
  return (
    <div className="award">
      <div className="ico">{icon}</div>
      <div className="t">{title}</div>
      <div className="prize">{prize || <span className="dim">Prize not yet confirmed</span>}</div>
      <div className="who">{who}</div>
      <div className="small muted" style={{ marginTop: 4 }}>{sub}</div>
      <div className="row" style={{ marginTop: 10, gap: 6 }}><StateTag state={state} />{extra}</div>
    </div>
  )
}

export function AwardsGrid({ awards, revenue }: { awards: Awards; revenue: RevenueSummary }) {
  const w = awards.weekly_demo
  const names = (l: { bd_name: string }[]) => (l.length ? l.map((x) => x.bd_name).join(' & ') : '—')
  const prev = w.previous_week
  return (
    <div className="awards">
      <AwardCard title={w.title} prize={w.prize} icon={<Medal size={26} />}
        who={names(w.provisional_leaders)} state={w.current_week ? 'provisional' : 'upcoming'}
        sub={<>{w.current_week ? <>{w.current_week.label} · {w.provisional_leaders[0]?.total ?? 0} qualified · announced {fmtDay(w.current_week.announce_on)}</> : 'No week in progress'}
          {w.current_tie && <div className="amber">Tie for the lead</div>}
          {prev && <div style={{ marginTop: 4 }}>Last week: <b>{names(prev.finalized?.result?.leaders ?? prev.leaders)}</b> {prev.state === 'finalized' ? '(final)' : '(awaiting finalisation)'}</div>}</>} />
      <AwardCard title={awards.league_champion.title} prize={awards.league_champion.prize} icon={<Trophy size={26} />}
        who={names(awards.league_champion.leaders)} state={awards.league_champion.state}
        sub={<>{awards.league_champion.leaders[0]?.total ?? 0} qualified completed demos (F2F + Virtual){awards.league_champion.tie && <div className="amber">Tie — flagged for admin review</div>}</>} />
      <AwardCard title={awards.revenue.title} prize={awards.revenue.prize} icon={<TrendingUp size={26} />}
        who={names(awards.revenue.champions)} state={awards.revenue.state}
        sub={<>{awards.revenue.champions.length ? fmtINR(awards.revenue.champions[0].total_inr) : `No BD at ${fmtLakh(revenue.threshold_inr)} yet`} · {awards.revenue.eligible_count} eligible
          {awards.revenue.tie && <div className="gold">Tie — prize split equally ({fmtINR(awards.revenue.champions[0].prize_share_inr)} each)</div>}</>} />
      <AwardCard title={awards.f2f.title} prize={awards.f2f.prize} icon={<Plane size={26} />}
        who={names(awards.f2f.leaders)} state={awards.f2f.state}
        sub={<>{awards.f2f.leaders[0]?.f2f ?? 0} qualified completed F2F demos{awards.f2f.tie && <div className="amber">{awards.f2f.tie_note}</div>}</>} />
    </div>
  )
}

/* ------------------------------------------------------------------ activity */
const ACT_ICON: Record<string, ReactNode> = {
  new_leader: <Crown size={15} color="var(--gold)" />, rank_change: <TrendingUp size={15} color="var(--blue)" />,
  qualified_demo: <CheckCircle2 size={15} color="var(--green)" />, demo_completed: <CheckCircle2 size={15} color="var(--green)" />,
  demo_scheduled: <CalendarCheck size={15} color="var(--blue)" />, revenue_updated: <IndianRupee size={15} color="var(--green)" />,
  revenue_champion: <Crown size={15} color="var(--gold)" />, poc_initiated: <Sparkles size={15} color="var(--violet)" />,
  poc_completed: <Sparkles size={15} color="var(--gold)" />, f2f_milestone: <Trophy size={15} color="var(--gold)" />,
  award_finalized: <Trophy size={15} color="var(--gold)" />, import: <Upload size={15} color="var(--muted)" />,
  day_closed: <CalendarCheck size={15} color="var(--muted)" />,
}

export function ActivityFeed({ items, limit = 12 }: { items: Activity[]; limit?: number }) {
  if (!items.length) return <div className="small muted">No activity yet.</div>
  return (
    <div className="feed">
      <AnimatePresence initial={false}>
        {items.slice(0, limit).map((a) => (
          <motion.div key={a.id} className="feed-item" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
            <div className="feed-ico">{ACT_ICON[a.kind] || <ActIcon size={15} color="var(--muted)" />}</div>
            <div>{a.message}{a.actor && <span className="dim tiny"> · {a.actor}</span>}</div>
            <div className="tiny dim nowrap" title={new Date(a.at).toLocaleString()}>{timeAgo(a.at)}</div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}

/* ------------------------------------------------------------------ motivation */
export function Motivation({ messages, every = 9000, className = 'motto' }: { messages: string[]; every?: number; className?: string }) {
  const [i, setI] = useState(() => (messages.length ? new Date().getDate() % messages.length : 0))
  useEffect(() => {
    if (messages.length < 2) return
    const t = setInterval(() => setI((x) => (x + 1) % messages.length), every)
    return () => clearInterval(t)
  }, [messages.length, every])
  if (!messages.length) return null
  return (
    <div className={className} aria-live="polite">
      <AnimatePresence mode="wait">
        <motion.div key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.35 }}>
          “{messages[i % messages.length]}”
        </motion.div>
      </AnimatePresence>
    </div>
  )
}
