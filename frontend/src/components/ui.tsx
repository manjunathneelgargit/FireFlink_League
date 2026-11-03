import { animate, motion, AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { bdHue, initials } from '../lib/format'
import { reducedMotionActive } from '../lib/prefs'

/* ------------------------------------------------------------------ animated number */
export function AnimatedNumber({ value, format = (v: number) => Math.round(v).toLocaleString('en-IN'), duration = 0.9 }: {
  value: number; format?: (v: number) => string; duration?: number
}) {
  const ref = useRef<HTMLSpanElement>(null)
  const prev = useRef<number>(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (reducedMotionActive()) {
      el.textContent = format(value)
      prev.current = value
      return
    }
    const c = animate(prev.current, value, {
      duration, ease: [0.2, 0.8, 0.2, 1],
      onUpdate: (v) => { el.textContent = format(v) },
    })
    prev.current = value
    return () => c.stop()
  }, [value]) // eslint-disable-line react-hooks/exhaustive-deps
  return <span ref={ref}>{format(0)}</span>
}

/* ------------------------------------------------------------------ progress ring */
export function Ring({ value, max, size = 64, stroke = 7, color = 'var(--green)', children }: {
  value: number; max: number; size?: number; stroke?: number; color?: string; children?: ReactNode
}) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const pct = max > 0 ? Math.min(1, value / max) : 0
  return (
    <div style={{ position: 'relative', width: size, height: size, flex: 'none' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }} aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="var(--surface3)" strokeWidth={stroke} fill="none" />
        <motion.circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={stroke} fill="none" strokeLinecap="round"
          strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - pct) }}
          transition={{ duration: 0.9, ease: [0.2, 0.8, 0.2, 1] }} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center' }}>{children}</div>
    </div>
  )
}

export function AnimatedCheck({ size = 22, color = 'var(--green)' }: { size?: number; color?: string }) {
  return (
    <svg className="check-draw" width={size} height={size} viewBox="0 0 24 24" fill="none" aria-label="achieved">
      <path d="M4 12.5l5 5L20 6.5" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/* ------------------------------------------------------------------ avatar */
export function Avatar({ id, name, size = 36 }: { id: number; name: string; size?: number }) {
  const h = bdHue(id)
  return (
    <div className="avatar" style={{ width: size, height: size, fontSize: size * 0.36, background: `linear-gradient(135deg, hsl(${h} 70% 48%), hsl(${h + 30} 70% 32%))` }}>
      {initials(name)}
    </div>
  )
}

/* ------------------------------------------------------------------ status pills */
const DAILY_CLS: Record<string, string> = {
  'Target Achieved': 'green', 'Target Missed': 'red', 'In Progress': 'blue', 'Target Pending Today': 'amber',
  'Carry-Forward Pending': 'amber', 'Not Started': 'grey',
}
export const DailyPill = ({ status }: { status: string }) => <span className={`pill ${DAILY_CLS[status] || 'grey'}`}>{status}</span>

const DEMO_CLS: Record<string, string> = {
  Completed: 'green', Scheduled: 'blue', 'No Show': 'red', Cancelled: 'red', Rescheduled: 'amber',
  'Awaiting Demo Date': 'grey', Pipeline: 'grey', 'POC Initiated': 'violet', 'POC In Progress': 'violet',
  'POC Completed': 'gold', 'POC Paused': 'amber',
}
export const StatusPill = ({ status }: { status: string }) => <span className={`pill ${DEMO_CLS[status] || 'grey'}`}>{status}</span>
export const TypePill = ({ type }: { type: string | null }) =>
  type ? <span className={`pill ${type === 'F2F' ? 'gold' : 'blue'}`}>{type}</span> : <span className="pill grey" title="Demo Type not set">—</span>

export const StateTag = ({ state }: { state: string }) =>
  state === 'finalized' ? <span className="tag-final">Final</span>
    : state === 'awaiting_finalization' ? <span className="tag-provisional">Awaiting finalisation</span>
      : state === 'upcoming' ? <span className="pill grey">Upcoming</span>
        : <span className="tag-provisional">Provisional</span>

/* ------------------------------------------------------------------ modal */
export function Modal({ title, onClose, children, wide, footer }: {
  title: ReactNode; onClose: () => void; children: ReactNode; wide?: boolean; footer?: ReactNode
}) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <motion.div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true"
        initial={{ opacity: 0, y: 14, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.18 }}>
        <div className="row" style={{ marginBottom: 14 }}>
          <h2>{title}</h2>
          <span className="spacer" />
          <button className="btn icon ghost" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        {children}
        {footer && <div className="modal-foot">{footer}</div>}
      </motion.div>
    </div>
  )
}

/* ------------------------------------------------------------------ confirm */
type ConfirmOpts = { title: string; body: ReactNode; confirm?: string; danger?: boolean }
const ConfirmCtx = createContext<(o: ConfirmOpts) => Promise<boolean>>(async () => false)
export const useConfirm = () => useContext(ConfirmCtx)

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<(ConfirmOpts & { resolve: (v: boolean) => void }) | null>(null)
  const ask = useCallback((o: ConfirmOpts) => new Promise<boolean>((resolve) => setState({ ...o, resolve })), [])
  const close = (v: boolean) => { state?.resolve(v); setState(null) }
  return (
    <ConfirmCtx.Provider value={ask}>
      {children}
      {state && (
        <Modal title={state.title} onClose={() => close(false)} footer={<>
          <button className="btn" onClick={() => close(false)}>Cancel</button>
          <button className={`btn ${state.danger ? 'danger' : 'primary'}`} onClick={() => close(true)} autoFocus>{state.confirm || 'Confirm'}</button>
        </>}>
          <div className="muted">{state.body}</div>
        </Modal>
      )}
    </ConfirmCtx.Provider>
  )
}

/* ------------------------------------------------------------------ toasts */
export type Toast = { id: number; tone: 'green' | 'amber' | 'red' | 'gold' | 'blue'; title: string; body?: string; icon?: ReactNode }
const ToastCtx = createContext<(t: Omit<Toast, 'id'>) => void>(() => {})
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((t: Omit<Toast, 'id'>) => {
    const id = Date.now() + Math.random()
    setItems((x) => [...x.slice(-4), { ...t, id }])
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), t.tone === 'red' ? 7000 : 5200)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        <AnimatePresence>
          {items.map((t) => (
            <motion.div key={t.id} className={`toast ${t.tone}`} initial={{ opacity: 0, x: 60 }} animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 60 }} transition={{ type: 'spring', stiffness: 380, damping: 30 }}>
              {t.icon}
              <div>
                <div className="tt">{t.title}</div>
                {t.body && <div className="small muted">{t.body}</div>}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  )
}

/* ------------------------------------------------------------------ misc */
export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { key: T; label: ReactNode }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={value === t.key} className={value === t.key ? 'on' : ''} onClick={() => onChange(t.key)}>{t.label}</button>
      ))}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>
}

export function Loading() {
  return <div className="empty"><span className="live-dot" /> Loading…</div>
}

export function MultiSelect({ options, value, onChange, placeholder }: {
  options: { value: string; label: string }[]; value: string[]; onChange: (v: string[]) => void; placeholder: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false)
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const label = value.length === 0 ? placeholder : value.length <= 2
    ? value.map((v) => options.find((o) => o.value === v)?.label ?? v).join(', ') : `${value.length} selected`
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button type="button" className="btn" style={{ width: '100%', justifyContent: 'space-between', fontWeight: 500, color: value.length ? 'var(--text)' : 'var(--muted)' }}
        onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span><span className="dim">▾</span>
      </button>
      {open && (
        <div className="card tight" style={{ position: 'absolute', zIndex: 40, top: 40, left: 0, right: 0, minWidth: 200, maxHeight: 280, overflow: 'auto', background: '#ffffff', boxShadow: 'var(--shadow)' }}>
          {options.length === 0 && <div className="small muted">No values</div>}
          {options.map((o) => (
            <label key={o.value} className="row small" style={{ padding: '4px 2px', cursor: 'pointer' }}>
              <input type="checkbox" checked={value.includes(o.value)}
                onChange={(e) => onChange(e.target.checked ? [...value, o.value] : value.filter((v) => v !== o.value))} />
              {o.label}
            </label>
          ))}
          {value.length > 0 && <button className="btn sm ghost" onClick={() => onChange([])}>Clear</button>}
        </div>
      )}
    </div>
  )
}
