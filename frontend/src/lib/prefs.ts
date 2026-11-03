import { useSyncExternalStore } from 'react'

const KEY = 'ffl_reduced_motion' // 'on' | 'off' | 'system'

function read(): 'on' | 'off' | 'system' {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'on' || v === 'off' ? v : 'system'
  } catch {
    return 'system'
  }
}

const listeners = new Set<() => void>()
const mq = typeof window !== 'undefined' ? window.matchMedia('(prefers-reduced-motion: reduce)') : null
mq?.addEventListener?.('change', () => listeners.forEach((l) => l()))

export function setReducedMotion(v: 'on' | 'off' | 'system') {
  try {
    localStorage.setItem(KEY, v)
  } catch { /* ignore */ }
  apply()
  listeners.forEach((l) => l())
}

export function reducedMotionActive(): boolean {
  const v = read()
  return v === 'on' || (v === 'system' && !!mq?.matches)
}

export function apply() {
  document.documentElement.dataset.reducedMotion = reducedMotionActive() ? 'true' : 'false'
}

export function useReducedMotion() {
  const setting = useSyncExternalStore((cb) => (listeners.add(cb), () => listeners.delete(cb)), read)
  const active = useSyncExternalStore((cb) => (listeners.add(cb), () => listeners.delete(cb)), reducedMotionActive)
  return { setting, active }
}
