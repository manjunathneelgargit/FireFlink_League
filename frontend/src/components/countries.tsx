import { useQuery } from '@tanstack/react-query'
import { Globe2, Plus, RefreshCw, X } from 'lucide-react'
import { useState } from 'react'
import { api, errorText } from '../api'

interface Country { name: string; aliases: string[] }
type Regions = Record<string, string[]>

const splitAliases = (s: string) => [...new Set(s.split(',').map((x) => x.trim().toLowerCase()).filter(Boolean))]

/**
 * F2F countries for a team: selected countries show as capsules (× removes them); the dropdown adds
 * more. Each country carries the spellings / cities it matches - editable under "advanced".
 * `team` lets the set-up wizard fetch with a specific team's header (the catalog is the same for all).
 */
export function CountryPicker({ value, onChange }: { value: Regions; onChange: (v: Regions) => void }) {
  const catalog = useQuery({ queryKey: ['countries'], queryFn: () => api.get<Country[]>('/api/countries'), staleTime: Infinity, retry: 1 })
  const [custom, setCustom] = useState('')
  const selected = Object.keys(value)
  const has = (n: string) => selected.some((s) => s.toLowerCase() === n.toLowerCase())
  const add = (name: string, aliases: string[]) => { if (name.trim() && !has(name)) onChange({ ...value, [name.trim()]: aliases }) }
  const remove = (name: string) => { const { [name]: _gone, ...rest } = value; onChange(rest) }
  const options = (catalog.data ?? []).filter((c) => !has(c.name))

  return (
    <div className="country-picker">
      <div className="chips" aria-live="polite">
        {selected.length === 0 && <span className="small amber">No F2F countries selected — F2F demos won't count until you add at least one.</span>}
        {selected.map((n) => (
          <span key={n} className="pill blue country-chip" title={value[n].join(', ')}>
            <Globe2 size={12} /> {n}
            <button type="button" className="chip-x" aria-label={`Remove ${n}`} onClick={() => remove(n)}><X size={12} /></button>
          </span>))}
      </div>
      {catalog.isError ? (
        <div className="notice amber row wrap" style={{ gap: 10 }}>
          <span className="small">Couldn't load the country list ({errorText(catalog.error)}). If the app was just updated, restart the server, then retry.</span>
          <button type="button" className="btn sm" onClick={() => catalog.refetch()}><RefreshCw size={13} /> Retry</button>
        </div>
      ) : (
        <select value="" aria-label="Add an F2F country" disabled={!catalog.data}
          onChange={(e) => { const c = catalog.data?.find((x) => x.name === e.target.value); if (c) add(c.name, c.aliases) }}>
          <option value="">{catalog.data ? 'Add a country…' : 'Loading countries…'}</option>
          {options.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
        </select>
      )}

      <details className="country-adv">
        <summary>Matching spellings & cities (advanced)</summary>
        <div className="tiny dim" style={{ margin: '6px 0 10px' }}>A demo counts for a country when its Country — or its City, if the Country doesn't match — equals one of these
          (case-insensitive; “Singapore, USA” is checked part by part). Add the spellings your sheet uses, e.g. “Malasia”.</div>
        <div className="form-grid">
          {selected.map((n) => <AliasField key={n} name={n} aliases={value[n]} onChange={(a) => onChange({ ...value, [n]: a })} />)}
        </div>
        <div className="row wrap" style={{ marginTop: 10 }}>
          <input style={{ maxWidth: 280 }} value={custom} placeholder="Custom region, e.g. Middle East" onChange={(e) => setCustom(e.target.value)} />
          <button type="button" className="btn sm" disabled={!custom.trim() || has(custom)} onClick={() => { add(custom, [custom.trim().toLowerCase()]); setCustom('') }}>
            <Plus size={13} /> Add custom region</button>
          <span className="tiny dim">Groups several countries under one name — then list each country and city in its spellings.</span>
        </div>
      </details>
    </div>
  )
}

/** Spellings textarea - edited as free text, saved (split on commas) when it loses focus. */
function AliasField({ name, aliases, onChange }: { name: string; aliases: string[]; onChange: (a: string[]) => void }) {
  const [text, setText] = useState(aliases.join(', '))
  return (
    <label className="field">{name}
      <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)}
        onBlur={() => { const a = splitAliases(text); if (a.length) { onChange(a); setText(a.join(', ')) } else setText(aliases.join(', ')) }} />
    </label>
  )
}
