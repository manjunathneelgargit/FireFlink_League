import { useQueryClient } from '@tanstack/react-query'
import { Eye, EyeOff, Lock } from 'lucide-react'
import { useState } from 'react'
import { api, errorText } from '../api'

export default function Login() {
  const qc = useQueryClient()
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    try {
      await api.post('/api/auth/login', { username: u, password: p })
      await qc.invalidateQueries({ queryKey: ['me'] })
      window.location.href = '/'
    } catch (ex) {
      setErr(errorText(ex))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="login-wrap">
      <form className="card login-card col" style={{ gap: 14, padding: 32, boxShadow: 'var(--shadow-lg)' }} onSubmit={submit}>
        <div className="row"><img src="/fireflink-logo.svg" width={30} alt="" />
          <div><div className="brand-word" style={{ fontSize: 24 }}>FIREFLINK</div>
            <div className="brand-sub">4.0 · Go Beyond – Ee Sala Market Namde!</div></div></div>
        <span className="eyebrow" style={{ alignSelf: 'flex-start' }}>League administrator</span>
        <h1 style={{ fontSize: 26, letterSpacing: '-0.02em' }}>Sign in to the league console</h1>
        <div className="muted small">League administrator sign-in. BDs don't need an account — this console is admin-only.</div>
        <label className="field">Username<input autoFocus autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} required /></label>
        <label className="field">Password
          <div className="pw-wrap">
            <input type={showPw ? 'text' : 'password'} autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} required />
            <button type="button" className="pw-toggle" aria-label={showPw ? 'Hide password' : 'Show password'} onClick={() => setShowPw((v) => !v)}>
              {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
        </label>
        {err && <div className="errors">{err}</div>}
        <button className="btn primary" disabled={busy}><Lock size={15} /> {busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </div>
  )
}
