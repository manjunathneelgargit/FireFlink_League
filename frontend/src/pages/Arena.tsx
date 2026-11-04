import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Crown, Maximize2, Medal, Plane, TrendingUp } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, errorText } from '../api'
import { Countdown, Motivation } from '../components/board'
import { useCelebrations } from '../components/celebrate'
import { AnimatedCheck, AnimatedNumber, Avatar, Ring } from '../components/ui'
import { fmtDay, fmtLakh, timeAgo } from '../lib/format'
import type { Snapshot } from '../types'

export default function Arena() {
  const token = new URLSearchParams(location.search).get('token')
  const [interval, setIv] = useState(30)
  const q = useQuery({
    queryKey: ['arena', token], refetchInterval: interval * 1000, refetchIntervalInBackground: true, retry: 2,
    queryFn: () => api.get<Snapshot>(`/api/arena${token ? `?token=${encodeURIComponent(token)}` : ''}`),
  })
  useEffect(() => { if (q.data) setIv(Math.max(10, q.data.league.arena_refresh_seconds || 30)) }, [q.data])
  const { hl, layer } = useCelebrations(q.data, 'arena')

  if (q.error) return <div className="login-wrap"><div className="card login-card"><h2 className="display">League Arena</h2>
    <div className="muted" style={{ margin: '8px 0 14px' }}>{errorText(q.error)}</div>
    <a className="btn primary" href="/login">Admin sign-in</a></div></div>
  const s = q.data
  if (!s) return <div className="login-wrap"><div className="muted"><span className="live-dot" /> Loading the Arena…</div></div>

  const leader = s.overall.filter((r) => r.is_leader)
  const anyScore = s.overall.some((r) => r.total > 0)
  const lowest = anyScore ? s.overall.filter((r) => r.is_lowest) : []
  const w = s.awards.weekly_demo
  const daily = s.daily
  const today = Object.values(daily.per_bd).sort((a, b) => a.bd_name.localeCompare(b.bd_name))

  return (
    <div className="arena theme-dark">
      {layer}
      <div className="arena-head">
        <img src="/fireflink-logo.svg" alt="" style={{ width: '2.6vw', minWidth: 30, filter: 'brightness(0) invert(1)' }} />
        <div>
          <div className="arena-title"><span style={{ background: 'linear-gradient(90deg,#e4cfe9,#ff6be1)', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>FireFlink 4.0</span> · Go Beyond</div>
          <div className="display" style={{ fontSize: 'clamp(16px,1.5vw,30px)', color: 'var(--lime)', fontWeight: 600 }}>Ee Sala Market Namde! <span className="arena-small"> · <span className="live-dot" /> live · {fmtDay(daily.today)}{s.sync?.enabled && s.sync.last_success ? ` · Google Sheet synced ${timeAgo(s.sync.last_success)}` : ''}</span></div>
        </div>
        <span className="spacer" />
        <Countdown endAt={s.league.end_at} phase={s.league.phase} />
        <button className="btn icon ghost" aria-label="Full screen" onClick={() => document.documentElement.requestFullscreen?.()}><Maximize2 size={18} /></button>
      </div>

      <div className="arena-grid">
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1vh' }}>
          <div className="card-head" style={{ marginBottom: 0 }}><h2>League leaderboard</h2><span className="arena-small">qualified completed demos · F2F + Virtual</span></div>
          {s.overall.map((r) => (
            <motion.div layout key={r.bd_id} transition={{ type: 'spring', stiffness: 220, damping: 26 }}
              className={`arena-lb-row ${r.is_leader ? 'leader shine' : ''} ${hl.gold.has(r.bd_id) ? 'anim-gold' : ''}`}>
              <div className="rk" style={{ position: 'relative' }}>{r.is_leader && <Crown className="crown" size={26} />}{r.rank}</div>
              <div className="row nm" style={{ minWidth: 0 }}><Avatar id={r.bd_id} name={r.bd_name} size={40} /><span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.bd_name}</span>
                {r.movement > 0 && <span className="move up">▲{r.movement}</span>}{r.movement < 0 && <span className="move down">▼{-r.movement}</span>}</div>
              <div className="hide-sm" style={{ textAlign: 'right' }}><div className="arena-small">F2F</div><b style={{ color: 'var(--fire)' }}>{r.f2f}</b></div>
              <div style={{ textAlign: 'right' }}><div className="arena-small">Virtual</div><b style={{ color: 'var(--blue)' }}>{r.virtual}</b></div>
              <div className="big"><AnimatedNumber value={r.total} /></div>
            </motion.div>
          ))}
          <div className="row wrap" style={{ gap: '1vw', marginTop: 'auto' }}>
            <div className="arena-small">Champion: <b className="gold">{leader.map((l) => l.bd_name).join(' & ') || '—'}</b></div>
            <div className="arena-small">Comeback zone: <b className="amber">{lowest.map((l) => l.bd_name).join(' & ') || '—'}</b> — one demo can change it!</div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.6vw', minHeight: 0 }}>
          <div className="award leader shine" style={{ width: '100%' }}><div className="ico"><Medal /></div><div className="t">Weekly leader</div>
            <div className="who">{w.provisional_leaders.map((l) => l.bd_name).join(' & ') || '—'}</div>
            <div className="arena-small">{w.current_week ? `${w.current_week.label} · ${w.provisional_leaders[0]?.total ?? 0} demos` : '—'}</div></div>
          <div className="card">
            <div className="card-head" style={{ marginBottom: '1vh' }}><h2>Today's targets</h2>
              <span className="arena-small">{daily.is_working_day && daily.within_league ? (daily.today_closed ? 'day closed' : `${s.kpis.on_target_today}/${s.kpis.bd_count} on target`) : 'non-working day'}</span></div>
            <div className="arena-today">
              {today.map((b) => {
                const t = b.today
                const ok = t?.status === 'Target Achieved'
                const miss = t?.status === 'Target Missed'
                return (
                  <div key={b.bd_id} className={`t ${ok ? 'ok' : miss ? 'miss' : ''} ${hl.glow.has(b.bd_id) ? 'anim-glow' : hl.pulse.has(b.bd_id) ? 'anim-pulse' : ''}`}>
                    <div className="row" style={{ justifyContent: 'space-between' }}><b>{b.bd_name}</b>
                      {t ? (ok ? <AnimatedCheck size={22} /> : <span className="num">{t.done}/{t.required}</span>) : <span className="arena-small">next {b.next_required ?? '—'}</span>}</div>
                    <div className="arena-small">{t ? (ok ? 'Target achieved' : miss ? `Carry ${t.pending_after} → next day` : t.pending_before ? `${t.pending_before} carried in` : 'In the race') : b.current_pending ? `${b.current_pending} pending` : 'All clear'}</div>
                  </div>
                )
              })}
            </div>
          </div>
          <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '1.4vw' }}>
            <Ring value={s.f2f.achieved} max={s.f2f.target} size={Math.max(110, Math.min(200, window.innerWidth * 0.1))} stroke={14} color="var(--fire)">
              <div style={{ textAlign: 'center' }}><div className="num" style={{ fontSize: 'clamp(28px,3vw,60px)', lineHeight: 1 }}>{s.f2f.achieved}</div><div className="arena-small">of {s.f2f.target}</div></div>
            </Ring>
            <div className="col" style={{ gap: '0.6vh' }}>
              <div className="display" style={{ fontSize: 'clamp(18px,1.6vw,32px)', fontWeight: 800 }}><Plane size={22} /> F2F {s.f2f.target} challenge</div>
              <div className="arena-small">{s.f2f.remaining} to go · {s.f2f.percent}% · {s.f2f.scheduled_pipeline.total} F2F scheduled</div>
              <div className="arena-small">Leader: <b className="gold">{s.f2f.leaders.map((l) => l.bd_name).join(' & ') || '—'}</b></div>
            </div>
          </div>
          <div className="award"><div className="ico"><TrendingUp /></div><div className="t">Revenue Champion</div>
            <div className="who">{s.revenue.champions.map((c) => c.bd_name).join(' & ') || '—'}</div>
            <div className="arena-small">{s.revenue.champions[0] ? fmtLakh(s.revenue.champions[0].total_inr) : 'No BD at ₹10L yet'} · total {fmtLakh(s.revenue.total_inr)}</div></div>
        </div>
      </div>
      <Motivation messages={s.league.motivational_messages} className="arena-motto" every={12000} />
    </div>
  )
}
