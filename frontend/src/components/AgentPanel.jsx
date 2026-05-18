import React from 'react'
import { CheckCircle2, Circle, Loader2, Zap, Euro, ShieldAlert, Activity } from 'lucide-react'

export default function AgentPanel({ steps, result }) {
    return (
        <div className="flex flex-col h-full space-y-6">
            <div className="glass-panel p-6 flex-1">
                <h3 className="text-lg font-medium mb-6 flex items-center gap-2">
                    <Activity className="w-5 h-5 text-accent" />
                    Agent Reasoning Steps
                </h3>
                
                <div className="space-y-4">
                    {steps.map((step, i) => (
                        <div key={i} className="flex items-start gap-3">
                            <div className="mt-0.5">
                                {step.status === 'done' ? (
                                    <CheckCircle2 className="w-5 h-5 text-accent" />
                                ) : step.status === 'active' ? (
                                    <Loader2 className="w-5 h-5 text-accent animate-spin" />
                                ) : (
                                    <Circle className="w-5 h-5 text-text3" />
                                )}
                            </div>
                            <div>
                                <span className={`text-sm font-medium ${
                                    step.status === 'active' ? 'text-text' : 
                                    step.status === 'done' ? 'text-text2' : 'text-text3'
                                }`}>
                                    {step.label}
                                </span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {result && (
                <div className="glass-panel p-6 animate-[fadeIn_0.5s_ease-out]">
                    <div className="flex justify-between items-start mb-4">
                        <h3 className="text-lg font-medium flex items-center gap-2">
                            <Zap className="w-5 h-5 text-warn" />
                            Analysis Result
                        </h3>
                        <span className="text-[10px] font-mono text-text3 bg-bg flex items-center px-2 py-1 rounded border border-border">
                            ID: {result.inspection_id.split('-')[0]}
                        </span>
                    </div>

                    <div className="space-y-4">
                        <div className="p-4 bg-bg rounded-lg border border-border">
                            <p className="text-sm text-text whitespace-pre-wrap leading-relaxed">
                                {result.root_cause}
                            </p>
                        </div>

                        {result.action_plan && result.action_plan.length > 0 && (
                            <div>
                                <h4 className="text-sm font-medium text-text2 mb-2 uppercase tracking-wider">Action Plan</h4>
                                <ul className="space-y-2">
                                    {result.action_plan.map((action, i) => (
                                        <li key={i} className="flex gap-2 text-sm text-text bg-bg3/50 p-2 rounded border border-border/50">
                                            <span className="text-accent font-mono">{i+1}.</span>
                                            {action}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        <div className="grid grid-cols-2 gap-3 mt-4">
                            <div className="bg-bg3 p-3 rounded-lg flex flex-col items-center justify-center border border-border">
                                <ShieldAlert className={`w-5 h-5 mb-1 ${result.eu_ai_act_tier.includes('High') ? 'text-danger' : 'text-accent'}`} />
                                <span className="text-xs text-text3 mb-1">EU AI Act Tier</span>
                                <span className="text-xs font-semibold text-center">{result.eu_ai_act_tier}</span>
                            </div>
                            <div className="bg-bg3 p-3 rounded-lg flex flex-col items-center justify-center border border-border">
                                <Euro className="w-5 h-5 mb-1 text-green-400" />
                                <span className="text-xs text-text3 mb-1">Est. Savings</span>
                                <span className="text-sm font-semibold text-green-400">€{result.estimated_savings_eur.toLocaleString()}</span>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
