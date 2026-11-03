/**
 * Detects genuine state TRANSITIONS between the last state this browser has seen and the new
 * snapshot. The first time a view is opened (no stored state) nothing is replayed, and refreshing
 * the page never replays a celebration because the "seen" state is persisted.
 */
import type { Snapshot } from '../types'

export interface SeenState {
  date: string
  today: Record<string, string> // bd_id -> daily status
  ranks: Record<string, number>
  leaders: number[]
  revChamps: number[]
  milestones: number[]
  finalized: string[] // award finalization ids
}

export type Celebration =
  | { kind: 'target_achieved'; bdId: number; name: string }
  | { kind: 'target_missed'; bdId: number; name: string; nextRequired: number | null }
  | { kind: 'new_leader'; names: string[]; bdIds: number[] }
  | { kind: 'rank_move'; bdId: number; dir: 'up' | 'down' }
  | { kind: 'f2f_milestone'; value: number; contributors: string[] }
  | { kind: 'revenue_champion'; names: string[] }
  | { kind: 'weekly_final'; label: string; names: string[] }
  | { kind: 'league_final'; names: string[]; total: number; title: string }

export function stateOf(s: Snapshot): SeenState {
  const fin: string[] = []
  for (const w of s.weeks) if (w.finalized) fin.push(`w:${w.finalized.id}`)
  for (const k of ['league_champion', 'revenue', 'f2f'] as const) {
    const f = s.awards[k].finalized
    if (f) fin.push(`${k}:${f.id}`)
  }
  return {
    date: s.daily.today,
    today: Object.fromEntries(Object.values(s.daily.per_bd).map((b) => [b.bd_id, b.today?.status ?? ''])),
    ranks: Object.fromEntries(s.overall.map((r) => [r.bd_id, r.rank])),
    leaders: s.overall.filter((r) => r.is_leader).map((r) => r.bd_id).sort(),
    revChamps: s.revenue.champions.map((c) => c.bd_id).sort(),
    milestones: s.f2f.milestones.filter((m) => m.reached).map((m) => m.value),
    finalized: fin,
  }
}

const same = (a: number[], b: number[]) => a.length === b.length && a.every((x, i) => x === b[i])

export function diff(prev: SeenState | null, s: Snapshot): Celebration[] {
  if (!prev) return []
  const next = stateOf(s)
  const out: Celebration[] = []
  const name = (id: number | string) => s.overall.find((r) => String(r.bd_id) === String(id))?.bd_name ?? ''
  if (prev.date === next.date) {
    for (const [id, st] of Object.entries(next.today)) {
      const was = prev.today[id]
      if (st === 'Target Achieved' && was !== 'Target Achieved' && was !== undefined)
        out.push({ kind: 'target_achieved', bdId: +id, name: name(id) })
      if (st === 'Target Missed' && was !== 'Target Missed' && was !== undefined)
        out.push({ kind: 'target_missed', bdId: +id, name: name(id), nextRequired: s.daily.per_bd[id]?.next_required ?? null })
    }
  }
  if (next.leaders.length && !same(prev.leaders, next.leaders))
    out.push({ kind: 'new_leader', bdIds: next.leaders, names: next.leaders.map(name) })
  for (const [id, r] of Object.entries(next.ranks)) {
    const was = prev.ranks[id]
    if (was && r !== was) out.push({ kind: 'rank_move', bdId: +id, dir: r < was ? 'up' : 'down' })
  }
  for (const m of next.milestones)
    if (!prev.milestones.includes(m))
      out.push({ kind: 'f2f_milestone', value: m, contributors: s.f2f.leaderboard.filter((r) => r.f2f > 0).map((r) => r.bd_name) })
  if (next.revChamps.length && !same(prev.revChamps, next.revChamps))
    out.push({ kind: 'revenue_champion', names: next.revChamps.map(name) })
  for (const f of next.finalized) {
    if (prev.finalized.includes(f)) continue
    if (f.startsWith('w:')) {
      const w = s.weeks.find((x) => x.finalized && `w:${x.finalized.id}` === f)
      if (w) out.push({ kind: 'weekly_final', label: w.label, names: (w.finalized?.result?.leaders || []).map((l: any) => l.bd_name) })
    } else if (f.startsWith('league_champion:')) {
      const a = s.awards.league_champion
      const leaders = a.finalized?.result?.leaders || []
      out.push({ kind: 'league_final', names: leaders.map((l: any) => l.bd_name), total: leaders[0]?.total ?? 0, title: a.title })
    }
  }
  return out
}

export function loadSeen(scope: string): SeenState | null {
  try {
    const v = localStorage.getItem(`ffl_seen_${scope}`)
    return v ? (JSON.parse(v) as SeenState) : null
  } catch {
    return null
  }
}

export function saveSeen(scope: string, s: Snapshot) {
  try {
    localStorage.setItem(`ffl_seen_${scope}`, JSON.stringify(stateOf(s)))
  } catch { /* storage unavailable: animations simply won't fire */ }
}
