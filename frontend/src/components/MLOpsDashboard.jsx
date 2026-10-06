import React, { useEffect, useState } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts'
import { getMetrics } from '../lib/api'

const TOOLTIP = { backgroundColor: '#111419', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px' }
const COLORS = ['#ff3b5c', '#ff9500', '#00d4aa', '#0077ff', '#a78bfa']
const SEVERITY_COLOR = { critical: 'text-danger', warning: 'text-[#ff9500]', info: 'text-accent' }

// Every number on this page is computed by the backend from the logged inspections and alerts.
// Metrics the system cannot measure (RAGAS scores, OEE) are listed at the bottom instead of being shown.
export default function MLOpsDashboard() {
    const [data, setData] = useState(null)

    useEffect(() => {
        const fetchMetrics = () => {
            getMetrics().then(setData).catch(console.error)
        }
        fetchMetrics()
        const int = setInterval(fetchMetrics, 15000)
        return () => clearInterval(int)
    }, [])

    if (!data) return <div className="p-8 text-center text-text3 animate-pulse font-mono">LOADING METRICS...</div>

    const { totals, latency, alerts, hourly_defects, defect_distribution, not_measured } = data

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-4 gap-4">
                {[
                    { label: "Inspected Today", value: totals.inspected_today },
                    { label: "Defect Rate", value: `${totals.defect_rate_pct}%`, color: totals.defect_rate_pct > 5 ? 'text-danger' : 'text-accent' },
                    { label: "Last Hour", value: totals.inspections_last_hour },
                    { label: "Open Alerts", value: totals.open_alerts, color: totals.open_alerts > 0 ? 'text-danger' : 'text-accent' }
                ].map((stat, i) => (
                    <div key={i} className="glass-panel p-4 flex flex-col items-center justify-center text-center">
                        <span className="text-xs text-text3 uppercase tracking-wider mb-1">{stat.label}</span>
                        <span className={`text-2xl font-mono ${stat.color || 'text-text'}`}>{stat.value}</span>
                    </div>
                ))}
            </div>

            <div className="glass-panel p-4">
                <h3 className="text-sm font-medium text-text2 mb-3">
                    Stream Alerts {totals.open_alerts > 0 && <span className="text-danger">({totals.open_alerts} open)</span>}
                </h3>
                {alerts.length === 0 ? (
                    <p className="text-xs text-text3">No alerts yet. Alerts come from the stream worker (baseline of the first 150 frames, then drift and fault checks).</p>
                ) : (
                    <ul className="space-y-1 font-mono text-xs">
                        {alerts.map(a => (
                            <li key={a.id} className="flex gap-3">
                                <span className="text-text3 shrink-0">{a.timestamp}</span>
                                <span className={`shrink-0 uppercase ${SEVERITY_COLOR[a.severity] || 'text-text'}`}>{a.status}</span>
                                <span className="text-text2 shrink-0">{a.name}</span>
                                <span className="text-text3 truncate">{a.message}</span>
                            </li>
                        ))}
                    </ul>
                )}
            </div>

            <div className="grid grid-cols-2 gap-6">
                <div className="glass-panel p-4 h-[250px] flex flex-col">
                    <h3 className="text-sm font-medium text-text2 mb-4">Frames and defects per hour (24h, UTC)</h3>
                    <div className="flex-1">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={hourly_defects}>
                                <XAxis dataKey="hour" stroke="#5a6880" fontSize={10} tickLine={false} axisLine={false} />
                                <YAxis stroke="#5a6880" fontSize={10} tickLine={false} axisLine={false} allowDecimals={false} />
                                <Tooltip contentStyle={TOOLTIP} />
                                <Legend wrapperStyle={{ fontSize: 10 }} />
                                <Area type="monotone" dataKey="frames" name="frames" stroke="#0077ff" fill="#0077ff" fillOpacity={0.12} strokeWidth={2} />
                                <Area type="monotone" dataKey="count" name="with a defect" stroke="#ff3b5c" fill="#ff3b5c" fillOpacity={0.25} strokeWidth={2} />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="glass-panel p-4 h-[250px] flex flex-col">
                    <h3 className="text-sm font-medium text-text2 mb-4">Defect Distribution</h3>
                    <div className="flex-1">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie data={defect_distribution} innerRadius={40} outerRadius={70} paddingAngle={5} dataKey="value" stroke="none">
                                    {defect_distribution.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                    ))}
                                </Pie>
                                <Tooltip contentStyle={TOOLTIP} />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                    <div className="flex flex-wrap gap-2 justify-center mt-2">
                        {defect_distribution.map((entry, i) => (
                            <div key={i} className="flex items-center gap-1 text-[10px] text-text3">
                                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }}></div>
                                {entry.name}
                            </div>
                        ))}
                    </div>
                </div>

                <div className="glass-panel p-4 h-[150px] flex flex-col justify-center">
                    <h3 className="text-sm font-medium text-text2 mb-3">Inference latency (last {latency.n} frames)</h3>
                    {latency.n === 0 ? (
                        <p className="text-xs text-text3">No latency recorded yet.</p>
                    ) : (
                        <div className="flex gap-8 font-mono">
                            <div><div className="text-xs text-text3">p50</div><div className="text-xl">{latency.p50_ms} ms</div></div>
                            <div><div className="text-xs text-text3">p95</div><div className="text-xl">{latency.p95_ms} ms</div></div>
                        </div>
                    )}
                </div>

                <div className="glass-panel p-4 h-[150px] overflow-auto">
                    <h3 className="text-sm font-medium text-text2 mb-2">Not measured</h3>
                    <ul className="space-y-1 text-[11px] text-text3">
                        {not_measured.map((m, i) => <li key={i}><span className="text-text2">{m.metric}:</span> {m.reason}</li>)}
                    </ul>
                </div>
            </div>
        </div>
    )
}
