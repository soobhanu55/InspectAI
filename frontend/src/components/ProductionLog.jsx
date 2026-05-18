import React, { useEffect, useState } from 'react'
import { getLog } from '../lib/api'
import { Download } from 'lucide-react'

export default function ProductionLog() {
    const [logs, setLogs] = useState([])

    useEffect(() => {
        const fetchLogs = () => {
            getLog(20).then(setLogs).catch(console.error)
        }
        fetchLogs()
        const int = setInterval(fetchLogs, 15000)
        return () => clearInterval(int)
    }, [])

    const getSeverityStyle = (severity) => {
        switch(severity) {
            case 'high': return 'bg-danger/20 text-danger border-danger/50'
            case 'medium': return 'bg-warn/20 text-warn border-warn/50'
            case 'low': return 'bg-purple/20 text-purple border-purple/50'
            default: return 'bg-accent/20 text-accent border-accent/50'
        }
    }

    const downloadCSV = () => {
        const headers = "ID,Timestamp,Machine,Part,Defect,Severity\n"
        const csv = logs.map(l => `${l.id},${l.timestamp},${l.machine},${l.part_type},${l.defect_type},${l.severity}`).join("\n")
        const blob = new Blob([headers + csv], { type: 'text/csv' })
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'production_log.csv'
        a.click()
    }

    return (
        <div className="glass-panel p-6 flex flex-col h-[600px]">
            <div className="flex justify-between items-center mb-6">
                <h3 className="text-lg font-medium">Production Log</h3>
                <button onClick={downloadCSV} className="btn-secondary text-xs flex items-center gap-2 py-1">
                    <Download className="w-3 h-3" /> Export CSV
                </button>
            </div>
            
            <div className="flex-1 overflow-auto pr-2">
                <table className="w-full text-left border-collapse">
                    <thead className="sticky top-0 bg-bg2 z-10 text-xs uppercase tracking-wider text-text3 border-b border-border">
                        <tr>
                            <th className="pb-3 font-medium">Zeit</th>
                            <th className="pb-3 font-medium">Maschine</th>
                            <th className="pb-3 font-medium">Bauteil</th>
                            <th className="pb-3 font-medium">Defekt</th>
                            <th className="pb-3 font-medium">Status</th>
                        </tr>
                    </thead>
                    <tbody className="text-sm font-mono">
                        {logs.map((log, i) => (
                            <tr key={log.id} className="border-b border-border/50 hover:bg-bg3/50 transition-colors animate-[fadeIn_0.3s_ease-out]">
                                <td className="py-3 text-text3">{new Date(log.timestamp).toLocaleTimeString()}</td>
                                <td className="py-3">{log.machine}</td>
                                <td className="py-3">{log.part_type}</td>
                                <td className="py-3">{log.defect_type !== 'none' ? log.defect_type : 'OK'}</td>
                                <td className="py-3">
                                    <span className={`px-2 py-0.5 rounded text-[10px] border ${getSeverityStyle(log.severity)} uppercase`}>
                                        {log.severity !== 'none' ? log.severity : 'PASS'}
                                    </span>
                                </td>
                            </tr>
                        ))}
                        {logs.length === 0 && (
                            <tr><td colSpan="5" className="py-8 text-center text-text3">No logs available.</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    )
}
