import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowLeft, ArrowRight, Check, CheckCircle2, Globe2, KeyRound, Plus, RefreshCw, Search, Sheet, UsersRound, X } from 'lucide-react'
import { useState } from 'react'
import { api, errorText, setTeamId, teamApi } from '../api'
import { CountryPicker } from './countries'
import { Loading, Modal, PasswordInput, useToast } from './ui'

export interface SetupTeam { id: number; name: string }
interface TeamOption { id: number; name: string }
interface UserRow { id: number; username: string; role: string; team_id: number | null }
interface BD { id: number; name: string; active: boolean; display_order: number }
interface SheetCheck {
  ok: boolean; sheet_names: string[]; bd_names: string[]; unknown_bds: string[]
  sheets: { sheet: string; found: boolean; missing: string[]; rows: number; headers: string[] }[]
}

const STEPS = [
  { key: 'team', label: 'Team', icon: UsersRound },
  { key: 'login', label: 'Login', icon: KeyRound },
  { key: 'bds', label: 'BD members', icon: UsersRound },
  { key: 'sheet', label: 'League & Google Sheet', icon: Sheet },
] as const

/**
 * Guided set-up for one team: 1) create/rename the team, 2) its login(s), 3) its BD members,
 * 4) league settings + Google Sheet. Every step saves immediately, so the wizard can be closed and
 * resumed later with "Set up" on the team's row.
 */
export function TeamSetupWizard({ team, teams, startStep = 0, onClose }: {
  team: SetupTeam | null; teams: TeamOption[]; startStep?: number; onClose: () => void
}) {
  const qc = useQueryClient()
  const [current, setCurrent] = useState<SetupTeam | null>(team)
  const [step, setStep] = useState(team ? startStep : 0)
  const [done, setDone] = useState(false)
  const changed = () => { qc.invalidateQueries({ queryKey: ['teams'] }); qc.invalidateQueries({ queryKey: ['users'] }); qc.invalidateQueries({ queryKey: ['me'] }) }
  const go = (n: number) => { changed(); setStep(n) }

  return (
    <Modal wide title={current ? `Set up team · ${current.name}` : 'New team'} onClose={() => { changed(); onClose() }}>
      <ol className="stepper" aria-label="Set-up steps">
        {STEPS.map((s, i) => {
          const state = done || i < step ? 'done' : i === step ? 'current' : 'todo'
          return (
            <li key={s.key} className={state}>
              <button type="button" disabled={!current || done} onClick={() => setStep(i)} aria-current={state === 'current' ? 'step' : undefined}>
                <span className="dot">{state === 'done' ? <Check size={14} /> : i + 1}</span>
                <span className="lbl">{s.label}</span>
              </button>
            </li>
          )
        })}
      </ol>

      {done && current ? <Finished team={current} onClose={() => { changed(); onClose() }} /> : <>
        {step === 0 && <StepTeam team={current} teams={teams} onSaved={(t) => { setCurrent(t); go(1) }} />}
        {step === 1 && current && <StepLogin team={current} onBack={() => setStep(0)} onNext={() => go(2)} />}
        {step === 2 && current && <StepBDs team={current} onBack={() => setStep(1)} onNext={() => go(3)} />}
        {step === 3 && current && <StepSheet team={current} onBack={() => setStep(2)} onFinish={() => { changed(); setDone(true) }} />}
      </>}
    </Modal>
  )
}

function Nav({ onBack, children }: { onBack?: () => void; children: React.ReactNode }) {
  return (
    <div className="modal-foot">
      {onBack && <button type="button" className="btn ghost" onClick={onBack}><ArrowLeft size={14} /> Back</button>}
      <span className="spacer" />
      {children}
    </div>
  )
}

/* ------------------------------------------------------------------ 1. team */
function StepTeam({ team, teams, onSaved }: { team: SetupTeam | null; teams: TeamOption[]; onSaved: (t: SetupTeam) => void }) {
  const toast = useToast()
  const [name, setName] = useState(team?.name ?? '')
  const [copyFrom, setCopyFrom] = useState('')
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try {
      if (!team) {
        const t = await api.post<SetupTeam>('/api/teams', { name, copy_settings_from: copyFrom ? Number(copyFrom) : null })
        onSaved(t)
      } else {
        if (name.trim() !== team.name) await api.put(`/api/teams/${team.id}`, { name })
        onSaved({ ...team, name: name.trim() })
      }
    } catch (e) { toast({ tone: 'red', title: 'Team not saved', body: errorText(e) }) } finally { setBusy(false) }
  }
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (name.trim().length >= 2) save() }}>
      <div className="step-intro">Give the team a name. Everything you set up next (login, BD members, league dates, Google Sheet) belongs only to this team.</div>
      <div className="form-grid">
        <label className="field"><span>Team name <span className="req">*</span></span><input autoFocus value={name} placeholder="e.g. India West" onChange={(e) => setName(e.target.value)} /></label>
        {!team && <label className="field">Start league settings from
          <select value={copyFrom} onChange={(e) => setCopyFrom(e.target.value)}>
            <option value="">Defaults (1 Nov – 20 Dec 2026, 1 demo/day, 23:59 cutoff)</option>
            {teams.map((t) => <option key={t.id} value={t.id}>Copy from {t.name}</option>)}
          </select></label>}
      </div>
      {!team && <div className="tiny dim" style={{ marginTop: 6 }}>You can change every setting in step 4. Google Sheet link and Arena link are never copied.</div>}
      <Nav><button className="btn primary" disabled={busy || name.trim().length < 2}>{team ? 'Save & continue' : 'Create team & continue'} <ArrowRight size={14} /></button></Nav>
    </form>
  )
}

/* ------------------------------------------------------------------ 2. login */
function StepLogin({ team, onBack, onNext }: { team: SetupTeam; onBack: () => void; onNext: () => void }) {
  const toast = useToast()
  const users = useQuery({ queryKey: ['users'], queryFn: () => api.get<UserRow[]>('/api/users') })
  const [f, setF] = useState({ username: '', password: '' })
  const [busy, setBusy] = useState(false)
  const mine = (users.data ?? []).filter((u) => u.role === 'team_admin' && u.team_id === team.id)
  const valid = f.username.trim().length >= 3 && f.password.length >= 10
  const add = async () => {
    setBusy(true)
    try {
      await api.post('/api/users', { username: f.username.trim(), password: f.password, role: 'team_admin', team_id: team.id })
      toast({ tone: 'green', title: `Login ${f.username.trim()} created`, body: `Share the username and password with the ${team.name} admin.` })
      setF({ username: '', password: '' }); users.refetch()
    } catch (e) { toast({ tone: 'red', title: 'Login not created', body: errorText(e) }) } finally { setBusy(false) }
  }
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (valid) add() }}>
      <div className="step-intro">Create the login the {team.name} team admin will use. It only ever sees {team.name}'s data. You can add more than one.</div>
      {mine.length > 0 && <div className="chips" style={{ marginBottom: 12 }}>{mine.map((u) => <span key={u.id} className="pill green"><KeyRound size={12} /> {u.username}</span>)}</div>}
      <div className="form-grid">
        <label className="field">Username<input autoFocus value={f.username} autoComplete="off" placeholder={`e.g. ${team.name.toLowerCase().replace(/[^a-z0-9]+/g, '.')}.admin`} onChange={(e) => setF({ ...f, username: e.target.value })} /></label>
        <label className="field">Password (min 10)<PasswordInput autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></label>
      </div>
      <div className="row" style={{ marginTop: 10 }}><span className="spacer" />
        <button className="btn" disabled={busy || !valid}><Plus size={14} /> Create login</button></div>
      <Nav onBack={onBack}>
        <button type="button" className="btn primary" onClick={onNext}>{mine.length ? 'Continue' : 'Skip for now'} <ArrowRight size={14} /></button>
      </Nav>
    </form>
  )
}

/* ------------------------------------------------------------------ 3. BD members */
const splitNames = (s: string) => s.split(/[\n,]+/).map((x) => x.trim().replace(/\s+/g, ' ')).filter(Boolean)

function StepBDs({ team, onBack, onNext }: { team: SetupTeam; onBack: () => void; onNext: () => void }) {
  const toast = useToast()
  const t = teamApi(team.id)
  const bds = useQuery({ queryKey: ['setup-bds', team.id], queryFn: () => t.get<BD[]>('/api/bds') })
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const add = async (names: string[]) => {
    setBusy(true)
    const existing = new Set((bds.data ?? []).map((b) => b.name.toLowerCase()))
    const fresh: string[] = []
    for (const n of names) {  // first spelling wins; skip names the team already has
      if (!existing.has(n.toLowerCase())) { existing.add(n.toLowerCase()); fresh.push(n) }
    }
    const failed: string[] = []
    for (const n of fresh) {
      try { await t.post('/api/bds', { name: n }) } catch (e) { failed.push(`${n}: ${errorText(e)}`) }
    }
    if (failed.length) toast({ tone: 'red', title: 'Some BDs were not added', body: failed.join(' · ') })
    setText(''); await bds.refetch(); setBusy(false)
  }
  const remove = async (b: BD) => {
    try { await t.del(`/api/bds/${b.id}`) } catch {
      try { await t.put(`/api/bds/${b.id}`, { name: b.name, active: !b.active }) } catch (e) { toast({ tone: 'red', title: 'Not changed', body: errorText(e) }) }
    }
    bds.refetch()
  }
  const names = splitNames(text)
  return (
    <div>
      <div className="step-intro">Add the {team.name} BDs. Names must match the <b>BD</b> column of their Google Sheet exactly (case doesn't matter). You can also add them from the sheet in the next step.</div>
      {!bds.data ? <Loading /> : (
        <div className="chips" style={{ marginBottom: 12 }}>
          {bds.data.length === 0 && <span className="dim small">No BDs yet.</span>}
          {bds.data.map((b) => (
            <span key={b.id} className={`pill ${b.active ? 'blue' : 'grey'}`}>{b.name}{!b.active && ' (inactive)'}
              <button type="button" className="chip-x" aria-label={`Remove ${b.name}`} title="Remove (BDs with records are deactivated instead)" onClick={() => remove(b)}><X size={12} /></button></span>))}
        </div>)}
      <label className="field">Add BD names — one per line, or separated by commas
        <textarea rows={4} value={text} placeholder={'Asha\nRahul\nMeera'} onChange={(e) => setText(e.target.value)} /></label>
      <div className="row" style={{ marginTop: 10 }}><span className="tiny dim">{names.length ? `${names.length} name${names.length > 1 ? 's' : ''} to add` : ''}</span><span className="spacer" />
        <button className="btn" disabled={busy || !names.length} onClick={() => add(names)}><Plus size={14} /> Add BDs</button></div>
      <Nav onBack={onBack}>
        <button type="button" className="btn primary" onClick={onNext}>{bds.data?.length ? 'Continue' : 'Skip for now'} <ArrowRight size={14} /></button>
      </Nav>
    </div>
  )
}

/* ------------------------------------------------------------------ 4. league + sheet */
function StepSheet(props: { team: SetupTeam; onBack: () => void; onFinish: () => void }) {
  const q = useQuery({ queryKey: ['setup-settings', props.team.id], queryFn: () => teamApi(props.team.id).get<any>('/api/settings'), gcTime: 0 })
  return q.data ? <SheetForm {...props} initial={q.data} /> : <Loading />
}

function SheetForm({ team, initial, onBack, onFinish }: { team: SetupTeam; initial: any; onBack: () => void; onFinish: () => void }) {
  const toast = useToast()
  const t = teamApi(team.id)
  const [s, setS] = useState<any>(() => structuredClone(initial))
  const [check, setCheck] = useState<SheetCheck | null>(null)
  const [checking, setChecking] = useState(false)
  const [busy, setBusy] = useState(false)
  const set = (k: string, v: any) => setS((x: any) => ({ ...x, [k]: v }))

  const runCheck = async () => {
    setChecking(true); setCheck(null)
    try {
      setCheck(await t.post<SheetCheck>('/api/gsheet/check', { url: s.gsheet_url, count_requires_qualified: s.count_requires_qualified, f2f_from_location: s.f2f_from_location }))
    } catch (e) { toast({ tone: 'red', title: 'Could not read the sheet', body: errorText(e) }) } finally { setChecking(false) }
  }
  const addUnknown = async () => {
    if (!check) return
    const failed: string[] = []
    for (const n of check.unknown_bds) {
      try { await t.post('/api/bds', { name: n }) } catch (e) { failed.push(`${n}: ${errorText(e)}`) }
    }
    if (failed.length) toast({ tone: 'red', title: 'Some BDs were not added', body: failed.join(' · ') })
    else toast({ tone: 'green', title: `${check.unknown_bds.length} BD${check.unknown_bds.length > 1 ? 's' : ''} added` })
    runCheck()
  }
  const finish = async () => {
    setBusy(true)
    try {
      const { arena_link_enabled: _a, ...body } = s
      await t.put('/api/settings', body)
      if (s.gsheet_sync_enabled && s.gsheet_url) {
        try {
          const r = await t.post<any>('/api/gsheet/sync')
          const d = r.summary?.demos, rv = r.summary?.revenue
          toast({ tone: 'green', title: 'First sync done', body: `${d?.added ?? 0} demos and ${rv?.added ?? 0} revenue records loaded${(r.summary?.alerts ?? []).length ? ' — see alerts in League settings' : ''}.` })
        } catch (e) { toast({ tone: 'amber', title: 'Settings saved, but the first sync failed', body: errorText(e) }) }
      }
      onFinish()
    } catch (e) { toast({ tone: 'red', title: 'Not saved', body: errorText(e) }) } finally { setBusy(false) }
  }

  return (
    <div className="col" style={{ gap: 16 }}>
      <div className="step-intro">Point the app at {team.name}'s Google Sheet and set their league calendar. The sheet must be shared as <b>“Anyone with the link can view”</b> and use the tabs <span className="kbd">Demos_and_Pipelines</span> and <span className="kbd">League_Revenue</span>.</div>

      <section className="setup-section">
        <h3><Sheet size={16} /> Google Sheet</h3>
        <div className="row wrap" style={{ alignItems: 'flex-end' }}>
          <label className="field" style={{ flex: '1 1 420px' }}>Google Sheet link
            <input value={s.gsheet_url ?? ''} placeholder="https://docs.google.com/spreadsheets/d/…" onChange={(e) => { set('gsheet_url', e.target.value); setCheck(null) }} /></label>
          <button type="button" className="btn" disabled={checking || !s.gsheet_url} onClick={runCheck}>
            {checking ? <RefreshCw size={14} className="spin" /> : <Search size={14} />} Check sheet</button>
        </div>
        {check && <CheckResult check={check} onAddBds={addUnknown} />}
        <div className="form-grid" style={{ marginTop: 12 }}>
          <label className="field">Which completed demos count
            <div className="seg"><button type="button" className={s.count_requires_qualified ? 'on' : ''} onClick={() => { set('count_requires_qualified', true); setCheck(null) }}>Only Qualified = Yes</button>
              <button type="button" className={!s.count_requires_qualified ? 'on' : ''} onClick={() => { set('count_requires_qualified', false); setCheck(null) }}>Every Completed demo</button></div></label>
          <label className="field">F2F when Demo Type is blank
            <div className="seg"><button type="button" className={s.f2f_from_location ? 'on' : ''} onClick={() => { set('f2f_from_location', true); setCheck(null) }}>From Country / City</button>
              <button type="button" className={!s.f2f_from_location ? 'on' : ''} onClick={() => { set('f2f_from_location', false); setCheck(null) }}>Not counted as F2F</button></div></label>
          <label className="field">Live sync
            <div className="seg"><button type="button" className={s.gsheet_sync_enabled ? 'on' : ''} onClick={() => set('gsheet_sync_enabled', true)}>On</button>
              <button type="button" className={!s.gsheet_sync_enabled ? 'on' : ''} onClick={() => set('gsheet_sync_enabled', false)}>Off</button></div></label>
          <label className="field">Check every (seconds, min 30)<input type="number" min={30} value={s.gsheet_sync_interval_seconds} onChange={(e) => set('gsheet_sync_interval_seconds', Number(e.target.value))} /></label>
        </div>
      </section>

      <section className="setup-section">
        <h3><UsersRound size={16} /> League calendar & targets</h3>
        <div className="form-grid">
          <label className="field">League name<input value={s.league_name} onChange={(e) => set('league_name', e.target.value)} /></label>
          <label className="field">League start<input type="date" value={s.league_start} onChange={(e) => set('league_start', e.target.value)} /></label>
          <label className="field">League end<input type="date" value={s.league_end} onChange={(e) => set('league_end', e.target.value)} /></label>
          <label className="field">Daily target per BD<input type="number" min={1} max={20} value={s.daily_target} onChange={(e) => set('daily_target', Number(e.target.value))} /></label>
          <label className="field">End-of-day cutoff (auto close)<input type="time" value={s.day_cutoff_time} onChange={(e) => set('day_cutoff_time', e.target.value)} /></label>
          <label className="field">Office login<input type="time" value={s.office_login_time} onChange={(e) => set('office_login_time', e.target.value)} /></label>
          <label className="field">Time zone<input value={s.timezone} onChange={(e) => set('timezone', e.target.value)} /></label>
          <label className="field">F2F challenge target<input type="number" min={1} value={s.f2f_target} onChange={(e) => set('f2f_target', Number(e.target.value))} /></label>
          <label className="field">Revenue award threshold (₹)<input type="number" min={0} value={s.revenue_threshold_inr} onChange={(e) => set('revenue_threshold_inr', Number(e.target.value))} /></label>
        </div>
        <div className="tiny dim" style={{ marginTop: 6 }}>Working days are Monday–Saturday. Prizes, milestones and motivational messages can be changed later under League settings.</div>
      </section>

      <section className="setup-section">
        <h3><Globe2 size={16} /> F2F countries</h3>
        <div className="step-intro" style={{ marginBottom: 10 }}>Pick the countries where {team.name}'s face-to-face demos count toward the F2F challenge.</div>
        <CountryPicker value={s.f2f_regions} onChange={(v) => set('f2f_regions', v)} />
      </section>

      <Nav onBack={onBack}>
        <button type="button" className="btn primary" disabled={busy} onClick={finish}>
          {busy ? <RefreshCw size={14} className="spin" /> : <Check size={14} />} {s.gsheet_sync_enabled && s.gsheet_url ? 'Save & run first sync' : 'Save & finish'}</button>
      </Nav>
    </div>
  )
}

function CheckResult({ check, onAddBds }: { check: SheetCheck; onAddBds: () => void }) {
  return (
    <div className={`notice ${check.ok ? 'green' : 'amber'}`} style={{ marginTop: 12 }}>
      <div className="row" style={{ gap: 8, fontWeight: 600 }}>
        {check.ok ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
        {check.ok ? 'The sheet matches this team’s format.' : 'The sheet needs changes before it can sync.'}
      </div>
      <ul className="check-list">
        {check.sheets.map((sh) => (
          <li key={sh.sheet}>
            <span className="kbd">{sh.sheet}</span>{' '}
            {!sh.found ? <span className="red">tab not found{check.sheet_names.length ? ` (tabs in the sheet: ${check.sheet_names.join(', ')})` : ''}</span>
              : sh.missing.length ? <span className="red">missing column(s): {sh.missing.join(', ')}</span>
                : <span>{sh.rows} row{sh.rows === 1 ? '' : 's'} ready</span>}
          </li>))}
      </ul>
      {check.unknown_bds.length > 0 && (
        <div className="row wrap" style={{ marginTop: 8 }}>
          <span className="small">BD names in the sheet that this team doesn't have yet: <b>{check.unknown_bds.join(', ')}</b> — their rows won't sync until added.</span>
          <button type="button" className="btn sm" onClick={onAddBds}><Plus size={13} /> Add {check.unknown_bds.length === 1 ? 'this BD' : `these ${check.unknown_bds.length} BDs`}</button>
        </div>)}
      {check.unknown_bds.length === 0 && check.bd_names.length > 0 && <div className="small" style={{ marginTop: 6 }}>All {check.bd_names.length} BD names in the sheet are set up.</div>}
    </div>
  )
}

function Finished({ team, onClose }: { team: SetupTeam; onClose: () => void }) {
  const qc = useQueryClient()
  return (
    <div className="setup-done">
      <CheckCircle2 size={44} color="var(--green)" />
      <h3>{team.name} is set up</h3>
      <p className="muted">The team admin can sign in now and will only see {team.name}. You can change anything later — switch to {team.name} and use League settings or BD members, or press <b>Set up</b> on its row.</p>
      <div className="row" style={{ justifyContent: 'center', marginTop: 8 }}>
        <button className="btn ghost" onClick={onClose}>Close</button>
        <button className="btn primary" onClick={() => { setTeamId(team.id); qc.resetQueries(); onClose() }}>Switch to {team.name} <ArrowRight size={14} /></button>
      </div>
    </div>
  )
}

