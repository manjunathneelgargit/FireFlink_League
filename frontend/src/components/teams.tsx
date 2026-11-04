import { useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Plus, Settings2, Trash2, UsersRound } from 'lucide-react'
import { useState } from 'react'
import { api, errorText, setTeamId } from '../api'
import type { Me } from '../types'
import { TeamSetupWizard, type SetupTeam } from './teamSetup'
import { Loading, Modal, PasswordInput, useConfirm, useToast } from './ui'

interface TeamRow {
  id: number; name: string; slug: string; active: boolean; created_at: string
  bds: number; demos: number; revenue: number; logins: number; sheet_url: string | null; live_sync: boolean
}
interface UserRow { id: number; username: string; role: 'super_admin' | 'team_admin'; team_id: number | null; team_name: string | null; created_at: string }

/** Super admin only: create teams and the logins that belong to them. */
export function TeamsAdmin() {
  const qc = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const me = useQuery({ queryKey: ['me'], queryFn: () => api.get<Me>('/api/auth/me') })
  const teams = useQuery({ queryKey: ['teams'], queryFn: () => api.get<TeamRow[]>('/api/teams') })
  const users = useQuery({ queryKey: ['users'], queryFn: () => api.get<UserRow[]>('/api/users') })
  const [wizard, setWizard] = useState<{ team: SetupTeam | null; step: number } | null>(null)
  const [newUser, setNewUser] = useState({ username: '', password: '', role: 'team_admin', team_id: '' })
  const [reset, setReset] = useState<UserRow | null>(null)
  const [resetPw, setResetPw] = useState('')

  if (!teams.data || !users.data || !me.data) return <Loading />
  const reload = () => { qc.invalidateQueries({ queryKey: ['teams'] }); qc.invalidateQueries({ queryKey: ['users'] }); qc.invalidateQueries({ queryKey: ['me'] }) }
  const fail = (title: string) => (e: unknown) => toast({ tone: 'red', title, body: errorText(e) })

  const toggleTeam = async (t: TeamRow) => {
    if (t.active && !(await confirm({ title: `Deactivate ${t.name}?`, body: 'Its logins are locked out and its sheet stops syncing. Data is kept and the team can be re-activated.' }))) return
    try { await api.put(`/api/teams/${t.id}`, { active: !t.active }); reload() } catch (e) { fail('Not changed')(e) }
  }
  const renameTeam = async (t: TeamRow) => {
    const name = window.prompt('New team name', t.name)?.trim()
    if (!name || name === t.name) return
    try { await api.put(`/api/teams/${t.id}`, { name }); reload() } catch (e) { fail('Not renamed')(e) }
  }
  const openTeam = (id: number) => { setTeamId(id); qc.resetQueries() }

  const addUser = async () => {
    try {
      await api.post('/api/users', { ...newUser, team_id: newUser.role === 'team_admin' ? Number(newUser.team_id) || null : null })
      toast({ tone: 'green', title: `Login ${newUser.username} created` })
      setNewUser({ username: '', password: '', role: 'team_admin', team_id: '' }); reload()
    } catch (e) { fail('Login not created')(e) }
  }
  const moveUser = async (u: UserRow, team_id: string) => {
    try {
      await api.put(`/api/users/${u.id}`, team_id === 'super' ? { role: 'super_admin' } : { role: 'team_admin', team_id: Number(team_id) })
      reload()
    } catch (e) { fail('Not changed')(e) }
  }
  const delUser = async (u: UserRow) => {
    if (!(await confirm({ title: `Delete login ${u.username}?`, body: 'They are signed out immediately.' }))) return
    try { await api.del(`/api/users/${u.id}`); reload() } catch (e) { fail('Not deleted')(e) }
  }
  const doReset = async () => {
    if (!reset) return
    try {
      await api.put(`/api/users/${reset.id}`, { password: resetPw })
      toast({ tone: 'green', title: `Password reset for ${reset.username}`, body: 'They have been signed out everywhere.' })
      setReset(null); setResetPw('')
    } catch (e) { fail('Not reset')(e) }
  }

  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="notice">Each team has its own BD members, demos, revenue, leaderboards, Google Sheet link, league dates and Arena link — teams never see each other's data.
        Team admins only see their own team. As super admin you switch teams with the selector in the top bar.</div>

      <div className="card">
        <div className="card-head"><UsersRound size={18} /><h3>Teams</h3><span className="hint">Set up: team → login → BD members → league & Google Sheet</span><span className="spacer" />
          <button className="btn primary" onClick={() => setWizard({ team: null, step: 0 })}><Plus size={14} /> New team</button></div>
        <div className="table-wrap"><table className="data">
          <thead><tr><th>Team</th><th>Status</th><th className="num">BDs</th><th className="num">Demos</th><th className="num">Revenue</th><th className="num">Logins</th><th>Google Sheet</th><th></th></tr></thead>
          <tbody>{teams.data.map((t) => (
            <tr key={t.id}>
              <td><b>{t.name}</b>{me.data.team.id === t.id && <span className="pill blue" style={{ marginLeft: 8 }}>viewing</span>}</td>
              <td><span className={`pill ${t.active ? 'green' : 'grey'}`}>{t.active ? 'Active' : 'Inactive'}</span></td>
              <td className="num">{t.bds}</td><td className="num">{t.demos}</td><td className="num">{t.revenue}</td><td className="num">{t.logins}</td>
              <td className="small">{t.sheet_url ? <>{t.live_sync ? <span className="pill green">Live</span> : <span className="pill grey">Off</span>} <a href={t.sheet_url} target="_blank" rel="noreferrer">Open sheet</a></> : <span className="dim">Not set</span>}</td>
              <td className="nowrap">
                <button className="btn sm" onClick={() => setWizard({ team: { id: t.id, name: t.name }, step: t.logins === 0 ? 1 : t.bds === 0 ? 2 : 3 })} title="Login, BD members, league dates and Google Sheet"><Settings2 size={13} /> Set up</button>{' '}
                {me.data.team.id !== t.id && t.active && <button className="btn sm ghost" onClick={() => openTeam(t.id)}>Switch to</button>}{' '}
                <button className="btn sm ghost" onClick={() => renameTeam(t)}>Rename</button>{' '}
                <button className={`btn sm ${t.active ? 'danger' : ''}`} onClick={() => toggleTeam(t)}>{t.active ? 'Deactivate' : 'Activate'}</button>
              </td>
            </tr>))}</tbody>
        </table></div>
      </div>

      <div className="card">
        <div className="card-head"><KeyRound size={18} /><h3>Logins</h3></div>
        <div className="table-wrap"><table className="data">
          <thead><tr><th>Username</th><th>Access</th><th>Created</th><th></th></tr></thead>
          <tbody>{users.data.map((u) => (
            <tr key={u.id}>
              <td><b>{u.username}</b>{u.username === me.data.username && <span className="tiny dim"> (you)</span>}</td>
              <td>
                <select value={u.role === 'super_admin' ? 'super' : String(u.team_id)} onChange={(e) => moveUser(u, e.target.value)} style={{ maxWidth: 240 }}>
                  <option value="super">Super admin — all teams</option>
                  {teams.data.map((t) => <option key={t.id} value={t.id}>Team admin — {t.name}</option>)}
                </select>
              </td>
              <td className="small nowrap">{new Date(u.created_at).toLocaleDateString()}</td>
              <td className="nowrap">
                <button className="btn sm ghost" onClick={() => { setReset(u); setResetPw('') }}><KeyRound size={13} /> Reset password</button>{' '}
                {u.username !== me.data.username && <button className="btn sm danger" onClick={() => delUser(u)} aria-label={`Delete ${u.username}`}><Trash2 size={13} /></button>}
              </td>
            </tr>))}</tbody>
        </table></div>
        <div className="section-label" style={{ marginTop: 16 }}>Add a login</div>
        <div className="form-grid">
          <label className="field">Username<input value={newUser.username} autoComplete="off" placeholder="e.g. emea.lead" onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} /></label>
          <label className="field">Password (min 10)<PasswordInput autoComplete="new-password" value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} /></label>
          <label className="field">Access
            <select value={newUser.role === 'super_admin' ? 'super' : newUser.team_id} onChange={(e) => setNewUser({ ...newUser, ...(e.target.value === 'super' ? { role: 'super_admin', team_id: '' } : { role: 'team_admin', team_id: e.target.value }) })}>
              <option value="">Choose a team…</option>
              {teams.data.filter((t) => t.active).map((t) => <option key={t.id} value={t.id}>Team admin — {t.name}</option>)}
              <option value="super">Super admin — all teams</option>
            </select></label>
        </div>
        <div className="row" style={{ marginTop: 10 }}><span className="spacer" />
          <button className="btn primary" disabled={newUser.username.trim().length < 3 || newUser.password.length < 10 || (newUser.role === 'team_admin' && !newUser.team_id)} onClick={addUser}><Plus size={14} /> Create login</button></div>
      </div>

      {wizard && <TeamSetupWizard team={wizard.team} startStep={wizard.step} teams={teams.data.map((t) => ({ id: t.id, name: t.name }))}
        onClose={() => { setWizard(null); reload() }} />}

      {reset && (
        <Modal title={`Reset password — ${reset.username}`} onClose={() => setReset(null)}
          footer={<><button className="btn ghost" onClick={() => setReset(null)}>Cancel</button><button className="btn primary" disabled={resetPw.length < 10} onClick={doReset}>Reset password</button></>}>
          <label className="field">New password (min 10)<PasswordInput autoComplete="new-password" value={resetPw} onChange={(e) => setResetPw(e.target.value)} autoFocus /></label>
        </Modal>
      )}
    </div>
  )
}
