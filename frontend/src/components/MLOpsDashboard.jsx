import React, { useEffect, useState } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, PieChart, Pie, Cell, BarChart, Bar } from 'recharts'
import { getMetrics } from '../lib/api'

export default function MLOpsDashboard() {
    const [data, setData] = useState(null)

    useEffect(() => {
        const fetchMetrics = () => {
            getMetrics().then(setData).catch(console.error)
        }
        fetchMetrics()
        const int = setInterval(fetchMetrics, 30000)
        return () => clearInterval(int)
    }, [])

    if (!data) return <div className="p-8 text-center text-text3 animate-pulse font-mono">LOADING METRICS...</div>

    const COLORS = ['#ff3b5c', '#ff9500', '#00d4aa', '#0077ff', '#a78bfa']

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-4 gap-4">
                {[
                    { label: "Inspected Today", value: data.totals.inspected_today },
                    { label: "Defect Rate", value: `${data.totals.defect_rate_pct}%`, color: data.totals.defect_rate_pct > 5 ? 'text-danger' : 'text-accent' },
                    { label: "OEE", value: `${data.totals.oee_pct}%` },
                    { label: "Inspections/hr", value: data.totals.inspections_per_hour }
                ].map((stat, i) => (
                    <div key={i} className="glass-panel p-4 flex flex-col items-center justify-center text-center">
                        <span className="text-xs text-text3 uppercase tracking-wider mb-1">{stat.label}</span>
                        <span className={`text-2xl font-mono ${stat.color || 'text-text'}`}>{stat.value}</span>
                    </div>
                ))}
            </div>

            <div className="grid grid-cols-2 gap-6">
                <div className="glass-panel p-4 h-[250px] flex flex-col">
                    <h3 className="text-sm font-medium text-text2 mb-4">Defects (24h)</h3>
                    <div className="flex-1">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={data.hourly_defects}>
                                <defs>
                                    <linearGradient id="colorDefects" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#ff3b5c" stopOpacity={0.3}/>
                                        <stop offset="95%" stopColor="#ff3b5c" stopOpacity={0}/>
                                    </linearGradient>
                                </defs>
                                <XAxis dataKey="hour" stroke="#5a6880" fontSize={10} tickLine={false} axisLine={false} />
                                <YAxis stroke="#5a6880" fontSize={10} tickLine={false} axisLine={false} />
                                <Tooltip contentStyle={{ backgroundColor: '#111419', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px' }} />
                                <Area type="monotone" dataKey="count" stroke="#ff3b5c" fillOpacity={1} fill="url(#colorDefects)" strokeWidth={2} />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="glass-panel p-4 h-[250px] flex flex-col">
                    <h3 className="text-sm font-medium text-text2 mb-4">OEE Trend (24h)</h3>
                    <div className="flex-1">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={data.hourly_oee}>
                                <XAxis dataKey="hour" stroke="#5a6880" fontSize={10} tickLine={false} axisLine={false} />
                                <YAxis stroke="#5a6880" fontSize={10} domain={['auto', 100]} tickLine={false} axisLine={false} />
                                <Tooltip contentStyle={{ backgroundColor: '#111419', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px' }} />
                                <Line type="monotone" dataKey="oee" stroke="#00d4aa" strokeWidth={2} dot={false} />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="glass-panel p-4 h-[250px] flex flex-col">
                    <h3 className="text-sm font-medium text-text2 mb-4">Defect Distribution</h3>
                    <div className="flex-1">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie data={data.defect_distribution} innerRadius={40} outerRadius={70} paddingAngle={5} dataKey="value" stroke="none">
                                    {data.defect_distribution.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                    ))}
                                </Pie>
                                <Tooltip contentStyle={{ backgroundColor: '#111419', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px' }} />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                    <div className="flex flex-wrap gap-2 justify-center mt-2">
                        {data.defect_distribution.map((entry, i) => (
                            <div key={i} className="flex items-center gap-1 text-[10px] text-text3">
                                <div className="w-2 h-2 rounded-full" style={{backgroundColor: COLORS[i % COLORS.length]}}></div>
                                {entry.name}
                            </div>
                        ))}
                    </div>
                </div>

                <div className="glass-panel p-4 h-[250px] flex flex-col">
                    <h3 className="text-sm font-medium text-text2 mb-4">RAGAS Evaluation</h3>
                    <div className="flex-1">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={[
                                { name: 'Faithful', value: data.ragas_scores.faithfulness * 100 },
                                { name: 'Relevancy', value: data.ragas_scores.answer_relevancy * 100 },
                                { name: 'Context', value: data.ragas_scores.context_precision * 100 }
                            ]} layout="vertical" margin={{ left: 20 }}>
                                <XAxis type="number" domain={[0, 100]} hide />
                                <YAxis dataKey="name" type="category" stroke="#5a6880" fontSize={10} tickLine={false} axisLine={false} />
                                <Tooltip cursor={{fill: 'rgba(255,255,255,0.05)'}} contentStyle={{ backgroundColor: '#111419', borderColor: 'rgba(255,255,255,0.1)' }} />
                                <Bar dataKey="value" fill="#a78bfa" radius={[0, 4, 4, 0]} barSize={12} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>
        </div>
    )
}
