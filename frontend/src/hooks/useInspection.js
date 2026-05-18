import { useState } from 'react'
import { inspectImage } from '../lib/api'

export function useInspection() {
    const [state, setState] = useState("idle") // idle | uploading | scanning | analyzing | complete | error
    const [file, setFile] = useState(null)
    const [preview, setPreview] = useState(null)
    const [result, setResult] = useState(null)
    const [agentSteps, setAgentSteps] = useState([])
    const [error, setError] = useState(null)
    
    const AGENT_STEPS = [
        "Image preprocessing",
        "YOLOv8n inference",
        "Defect classification",
        "Hybrid RAG retrieval",
        "Cross-encoder reranking",
        "LLM root cause analysis",
        "Action plan generation",
    ]
    
    const runInspection = async (machine, partType) => {
        if (!file) return
        setState("uploading")
        setResult(null)
        setAgentSteps(AGENT_STEPS.map((label, i) => ({
            label, status: i === 0 ? "active" : "pending"
        })))
        
        try {
            // Animate through steps while API call runs
            const stepTimer = simulateStepProgress(setAgentSteps, AGENT_STEPS)
            
            const data = await inspectImage(file, machine, partType)
            clearInterval(stepTimer)
            
            // Mark all done
            setAgentSteps(AGENT_STEPS.map(label => ({
                label, status: "done"
            })))
            
            setResult(data)
            setState("complete")
        } catch (err) {
            setError(err.message)
            setState("error")
        }
    }
    
    return { state, file, setFile, preview, setPreview,
             result, agentSteps, error, runInspection }
}

function simulateStepProgress(setSteps, steps) {
    let current = 0
    return setInterval(() => {
        current = Math.min(current + 1, steps.length - 1)
        setSteps(steps.map((label, i) => ({
            label,
            status: i < current ? "done" : i === current ? "active" : "pending"
        })))
    }, 600)
}
