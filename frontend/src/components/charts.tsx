import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const AXIS = { stroke: '#8f8494', fontSize: 11, tickLine: false, axisLine: false } as const
const GRID = { stroke: '#efe7f3', vertical: false } as const
const TIP = {
  contentStyle: { background: '#ffffff', border: '1px solid #ece4f0', borderRadius: 10, color: '#0e0a1a', boxShadow: '0 10px 30px rgba(41,16,45,.12)', fontSize: 12 },
  labelStyle: { color: '#52506a' }, cursor: { fill: 'rgba(113,52,123,.06)' },
}

/** Single-series horizontal bars (magnitude by category). Value labels in text ink, not series colour. */
export function HBars({ data, color = '#22a35a', format = (v: number) => String(v), height }: {
  data: { name: string; value: number }[]; color?: string; format?: (v: number) => string; height?: number
}) {
  if (!data.length) return <div className="small muted">No data yet.</div>
  return (
    <div style={{ width: '100%', height: height ?? Math.max(120, data.length * 34 + 20) }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 70, top: 4, bottom: 4 }} barCategoryGap={6}>
          <CartesianGrid {...GRID} horizontal={false} vertical />
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="name" width={130} {...AXIS} tick={{ fill: '#0e0a1a', fontSize: 12 }} />
          <Tooltip {...TIP} formatter={(v) => [format(Number(v)), '']} separator="" />
          <Bar dataKey="value" fill={color} radius={[0, 4, 4, 0]} maxBarSize={18} isAnimationActive
            label={{ position: 'right', fill: '#0e0a1a', fontSize: 12, formatter: (v: any) => format(Number(v)) }} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Single-series daily columns. */
export function DailyBars({ data, color = '#71347b', label = 'Qualified demos' }: { data: { date: string; value: number }[]; color?: string; label?: string }) {
  if (!data.length) return <div className="small muted">No data yet.</div>
  return (
    <div className="chart-box">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ left: -18, right: 8, top: 8, bottom: 0 }} barCategoryGap={2}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="date" {...AXIS} tickFormatter={(d) => d.slice(8) + '/' + d.slice(5, 7)} minTickGap={12} />
          <YAxis allowDecimals={false} {...AXIS} />
          <Tooltip {...TIP} formatter={(v) => [v as any, label]} />
          <Bar dataKey="value" fill={color} radius={[4, 4, 0, 0]} maxBarSize={22} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Single-series cumulative line with crosshair tooltip. */
export function CumulativeLine({ data, color = '#c026d3', label = 'Cumulative' }: { data: { date: string; value: number }[]; color?: string; label?: string }) {
  if (!data.length) return <div className="small muted">No data yet.</div>
  return (
    <div className="chart-box">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ left: -18, right: 8, top: 8, bottom: 0 }}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="date" {...AXIS} tickFormatter={(d) => d.slice(8) + '/' + d.slice(5, 7)} minTickGap={12} />
          <YAxis allowDecimals={false} {...AXIS} />
          <Tooltip {...TIP} cursor={{ stroke: 'rgba(113,52,123,.35)' }} formatter={(v) => [v as any, label]} />
          <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2} dot={false} activeDot={{ r: 5, stroke: '#ffffff', strokeWidth: 2 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
