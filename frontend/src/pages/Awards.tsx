import { Lock, Undo2 } from 'lucide-react'
import { useState } from 'react'
import { api, errorText } from '../api'
import { AwardsGrid, OverallLeaderboard, RevenueBoard } from '../components/board'
import { EMPTY_HIGHLIGHTS, useCelebrations } from '../components/celebrate'
import { Loading, StateTag, Tabs, useConfirm, useToast } from '../components/ui'
import { useRefreshAll, useSnapshot } from '../hooks'
import { fmtDay } from '../lib/format'
import type { Snapshot } from '../types'

export default function Awards() {
  const { data: s } = useSnapshot()
  const { hl, layer } = useCelebrations(s, 'awards', { toasts: false })
  const [tab, setTab] = useState<'overall' | 'weekly' | 'f2f' | 'revenue'>('weekly')
  if (!s) return <Loading />
  return (
    <>
      {layer}
      <div className="page-head"><div><h1>Awards & Leaderboards</h1>
        <div className="sub">Official standings always use complete league data (1 Nov – 20 Dec 2026). Report filters never change them.</div></div></div>
      <AwardsGrid awards={s.awards} revenue={s.revenue} />
      <div style={{ marginTop: 18 }} />
      <Tabs value={tab} onChange={setTab} tabs={[{ key: 'weekly', label: 'Weekly Demo Champion' }, { key: 'overall', label: 'Champion of the League' }, { key: 'f2f', label: 'F2F Champion' }, { key: 'revenue', label: 'Revenue Champion' }]} />
      {tab === 'weekly' && <Weekly s={s} />}
      {tab === 'overall' && (
        <div className="card">
          <div className="card-head"><h2>Overall league standings</h2><StateTag state={s.awards.league_champion.state} />
            <span className="hint">F2F + Virtual qualified completed demos · ties share a rank</span><span className="spacer" />
            <FinalizeButton s={s} awardKey="league_champion" periodKey="league" state={s.awards.league_champion.state} finalizedId={s.awards.league_champion.finalized?.id} /></div>
          {s.awards.league_champion.tie && <div className="notice amber" style={{ marginBottom: 10 }}>Tie for first — no tie-break rule is configured. Flagged for administrator review.</div>}
          <div className="small muted" style={{ marginBottom: 10 }}>Prize: {s.awards.league_champion.prize ?? 'not yet confirmed'}</div>
          <OverallLeaderboard rows={s.overall} hl={hl} />
        </div>
      )}
      {tab === 'f2f' && (
        <div className="card">
          <div className="card-head"><h2>F2F Champion</h2><StateTag state={s.awards.f2f.state} /><span className="hint">Qualified completed F2F demos · Malaysia, Singapore, Middle East</span><span className="spacer" />
            <FinalizeButton s={s} awardKey="f2f" periodKey="league" state={s.awards.f2f.state} finalizedId={s.awards.f2f.finalized?.id} /></div>
          {s.awards.f2f.tie && <div className="notice amber" style={{ marginBottom: 10 }}>{s.awards.f2f.tie_note}</div>}
          <div className="table-wrap"><table className="data">
            <thead><tr><th>Rank</th><th>BD</th><th className="num">Qualified completed F2F</th><th className="num">Scheduled F2F (pipeline)</th></tr></thead>
            <tbody>{s.f2f.leaderboard.map((r) => <tr key={r.bd_id}><td className="num" style={{ textAlign: 'left' }}>{r.rank}</td><td style={{ fontWeight: 600 }}>{r.f2f > 0 && r.rank === 1 ? '👑 ' : ''}{r.bd_name}</td><td className="num">{r.f2f}</td><td className="num">{r.scheduled_f2f}</td></tr>)}</tbody>
          </table></div>
        </div>
      )}
      {tab === 'revenue' && (
        <div className="card">
          <div className="card-head"><h2>Revenue Champion</h2><StateTag state={s.awards.revenue.state} /><span className="hint">≥ ₹10 lakh to qualify · tie splits ₹1,00,000 equally</span><span className="spacer" />
            <FinalizeButton s={s} awardKey="revenue" periodKey="league" state={s.awards.revenue.state} finalizedId={s.awards.revenue.finalized?.id} /></div>
          <RevenueBoard rev={s.revenue} hl={EMPTY_HIGHLIGHTS} />
        </div>
      )}
    </>
  )
}

function FinalizeButton({ s, awardKey, periodKey, state, finalizedId, label }: {
  s: Snapshot; awardKey: string; periodKey: string; state: string; finalizedId?: number; label?: string
}) {
  const confirm = useConfirm()
  const toast = useToast()
  const refresh = useRefreshAll()
  if (state === 'finalized' && finalizedId) {
    return <button className="btn sm ghost" onClick={async () => {
      if (!(await confirm({ title: 'Undo finalisation?', danger: true, body: 'The award goes back to provisional. This is recorded in the audit log.' }))) return
      try { await api.del(`/api/awards/finalize/${finalizedId}`); refresh() } catch (e) { toast({ tone: 'red', title: 'Failed', body: errorText(e) }) }
    }}><Undo2 size={14} /> Undo</button>
  }
  if (state !== 'awaiting_finalization') return <span className="small dim">{awardKey === 'weekly_demo' ? 'Finalise after the week ends' : `Finalise after ${fmtDay(s.league.end)}`}</span>
  return <button className="btn sm primary" onClick={async () => {
    if (!(await confirm({ title: `Finalise ${label ?? 'award'}?`, confirm: 'Finalise', body: 'This locks a snapshot of the current winner(s) as the official result and announces it with a celebration.' }))) return
    try { await api.post('/api/awards/finalize', { award_key: awardKey, period_key: periodKey }); refresh() } catch (e) { toast({ tone: 'red', title: 'Failed', body: errorText(e) }) }
  }}><Lock size={14} /> Finalise</button>
}

function Weekly({ s }: { s: Snapshot }) {
  return (
    <div className="col" style={{ gap: 12 }}>
      <div className="notice">Weeks run Monday–Sunday (configurable in Settings); 1 Nov (Sunday) is folded into Week 1. Winners are announced on the Monday after each week. Both F2F and Virtual qualified completed demos count.</div>
      {s.weeks.map((w) => {
        const fin = w.finalized?.result
        const leaders = (fin?.leaders ?? w.leaders) as { bd_name: string; total: number }[]
        return (
          <div key={w.key} className={`card ${w.state === 'in_progress' ? 'gold-edge' : ''}`} style={{ opacity: w.state === 'upcoming' ? 0.55 : 1 }}>
            <div className="card-head" style={{ marginBottom: w.state === 'upcoming' ? 0 : 12 }}>
              <h3>{w.label}</h3><StateTag state={w.state} />
              <span className="hint">Announce {fmtDay(w.announce_on)}</span><span className="spacer" />
              {w.state !== 'upcoming' && <span className="small">{w.state === 'finalized' ? 'Winner' : 'Leader'}: <b className="gold">{leaders.length ? leaders.map((l) => l.bd_name).join(' & ') : '—'}</b>{leaders[0] ? ` · ${leaders[0].total}` : ''}</span>}
              {(w.tie && w.state !== 'upcoming') && <span className="pill amber">Tie — admin review</span>}
              <FinalizeButton s={s} awardKey="weekly_demo" periodKey={w.key} state={w.state} finalizedId={w.finalized?.id} label={w.label} />
            </div>
            {w.state !== 'upcoming' && (
              <div className="row wrap" style={{ gap: 8 }}>
                {w.standings.map((r) => (
                  <div key={r.bd_id} className="pill grey" style={{ fontSize: 12.5, padding: '5px 10px', color: r.rank === 1 && r.total > 0 ? 'var(--gold)' : undefined }}>
                    #{r.rank} {r.bd_name} · <b>{r.total}</b> <span className="dim">({r.f2f} F2F / {r.virtual} V)</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
