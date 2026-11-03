import confetti from 'canvas-confetti'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, Crown, Trophy } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { diff, loadSeen, saveSeen, type Celebration } from '../lib/celebrations'
import { reducedMotionActive } from '../lib/prefs'
import type { Snapshot } from '../types'
import { AnimatedCheck, useToast } from './ui'

export interface Highlights {
  glow: Set<number> // daily target achieved
  pulse: Set<number> // missed after closure
  gold: Set<number> // leader / revenue champion change
  moved: Map<number, 'up' | 'down'>
  f2fMilestone: number | null
  revenueChanged: boolean
}

export const EMPTY_HIGHLIGHTS: Highlights = { glow: new Set(), pulse: new Set(), gold: new Set(), moved: new Map(), f2fMilestone: null, revenueChanged: false }

function burst(big = false) {
  if (reducedMotionActive()) return
  const colors = ['#f5c542', '#ffe08a', '#ff4fd8', '#c79fd0', '#71347b', '#4ade80']
  confetti({ particleCount: big ? 160 : 90, spread: big ? 110 : 75, origin: { y: 0.35 }, colors, scalar: 0.95, disableForReducedMotion: true })
  if (big) setTimeout(() => confetti({ particleCount: 120, angle: 60, spread: 70, origin: { x: 0, y: 0.6 }, colors, disableForReducedMotion: true }), 250)
  if (big) setTimeout(() => confetti({ particleCount: 120, angle: 120, spread: 70, origin: { x: 1, y: 0.6 }, colors, disableForReducedMotion: true }), 400)
}

/**
 * Compares the incoming snapshot with what this browser last saw for `scope` and fires effects
 * only for genuine transitions. Nothing replays on refresh/reopen.
 */
export function useCelebrations(snap: Snapshot | undefined, scope: string, opts: { toasts?: boolean } = { toasts: true }) {
  const toast = useToast()
  const [hl, setHl] = useState<Highlights>(EMPTY_HIGHLIGHTS)
  const [banner, setBanner] = useState<string | null>(null)
  const [overlay, setOverlay] = useState<Extract<Celebration, { kind: 'league_final' }> | null>(null)
  const [trophy, setTrophy] = useState<string | null>(null)
  const timers = useRef<number[]>([])

  useEffect(() => {
    if (!snap) return
    const events = diff(loadSeen(scope), snap)
    saveSeen(scope, snap)
    if (!events.length) return
    const next: Highlights = { glow: new Set(), pulse: new Set(), gold: new Set(), moved: new Map(), f2fMilestone: null, revenueChanged: false }
    for (const e of events) {
      switch (e.kind) {
        case 'target_achieved':
          next.glow.add(e.bdId)
          if (opts.toasts) toast({ tone: 'green', title: `Target Achieved! ${e.name}`, body: 'Great work. Keep the momentum going.', icon: <AnimatedCheck /> })
          break
        case 'target_missed':
          next.pulse.add(e.bdId)
          if (opts.toasts) toast({ tone: 'amber', icon: <AlertTriangle className="anim-shake" color="var(--amber)" size={20} />, title: `${e.name}: target carried forward`,
            body: `Today didn't go as planned. Tomorrow is your opportunity to bounce back${e.nextRequired ? ` — ${e.nextRequired} qualified demo${e.nextRequired > 1 ? 's' : ''} needed` : ''}. Clear your pending target and get back in the race!` })
          break
        case 'new_leader':
          e.bdIds.forEach((id) => next.gold.add(id))
          setBanner(`NEW LEADER! ${e.names.join(' & ')}`)
          timers.current.push(window.setTimeout(() => setBanner(null), 4200))
          break
        case 'rank_move':
          next.moved.set(e.bdId, e.dir)
          break
        case 'f2f_milestone':
          next.f2fMilestone = e.value
          setTrophy(`F2F milestone: ${e.value} qualified F2F demos!`)
          burst()
          timers.current.push(window.setTimeout(() => setTrophy(null), 4200))
          if (opts.toasts && e.contributors.length) toast({ tone: 'gold', icon: <Trophy color="var(--gold)" size={20} />, title: `F2F milestone ${e.value} reached`, body: `Contributors: ${e.contributors.join(', ')}` })
          break
        case 'revenue_champion':
          next.revenueChanged = true
          if (opts.toasts) toast({ tone: 'gold', icon: <Crown color="var(--gold)" size={20} />, title: 'Revenue Champion change', body: `${e.names.join(' & ')} now lead${e.names.length === 1 ? 's' : ''} the revenue race` })
          break
        case 'weekly_final':
          setTrophy(`${e.label} — Weekly Demo Champion: ${e.names.join(' & ') || 'no winner'}`)
          burst()
          timers.current.push(window.setTimeout(() => setTrophy(null), 5200))
          break
        case 'league_final':
          setOverlay(e)
          burst(true)
          break
      }
    }
    setHl(next)
    timers.current.push(window.setTimeout(() => setHl(EMPTY_HIGHLIGHTS), 6000))
  }, [snap]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => timers.current.forEach(clearTimeout), [])

  const layer = (
    <>
      <AnimatePresence>
        {banner && (
          <motion.div className="banner-top" initial={{ y: -80, opacity: 0, x: '-50%' }} animate={{ y: 0, opacity: 1, x: '-50%' }} exit={{ y: -80, opacity: 0, x: '-50%' }}
            transition={{ type: 'spring', stiffness: 300, damping: 22 }}>
            <Crown size={26} /> {banner}
          </motion.div>
        )}
        {trophy && (
          <motion.div className="banner-top" style={{ top: 80, fontSize: 20 }} initial={{ scale: 0.6, opacity: 0, x: '-50%' }} animate={{ scale: 1, opacity: 1, x: '-50%' }} exit={{ opacity: 0, x: '-50%' }}>
            <Trophy size={22} /> {trophy}
          </motion.div>
        )}
      </AnimatePresence>
      {overlay && (
        <div className="fullscreen-celebration" onClick={() => setOverlay(null)} role="dialog" aria-label="League champion">
          <motion.div initial={{ scale: 0.7, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: 'spring', stiffness: 160, damping: 14 }}>
            <Trophy size={110} color="var(--gold)" style={{ filter: 'drop-shadow(0 0 30px rgba(245,197,66,.6))' }} />
            <div className="upper gold" style={{ fontWeight: 800, marginTop: 10 }}>{overlay.title}</div>
            <div className="big">{overlay.names.join(' & ') || '—'}</div>
            <div className="display" style={{ fontSize: 30, marginTop: 10 }}>{overlay.total} qualified completed demos</div>
            <div className="muted" style={{ marginTop: 24 }}>FireFlink 4.0 – Go Beyond – Ee Sala Market Namde! · click anywhere to close</div>
          </motion.div>
        </div>
      )}
    </>
  )
  return { hl, layer }
}
