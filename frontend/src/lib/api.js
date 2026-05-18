const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:7860"

export async function inspectImage(file, machine, partType, batchId) {
    const form = new FormData()
    form.append("file", file)
    form.append("machine", machine)
    form.append("part_type", partType)
    form.append("batch_id", batchId || "")
    
    const res = await fetch(`${BASE_URL}/api/inspect`, {
        method: "POST",
        body: form,
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
}

export function streamChat(query, sessionId, machine, onChunk, onDone) {
    const url = new URL(`${BASE_URL}/api/chat`)
    url.searchParams.set("query", query)
    url.searchParams.set("session_id", sessionId)
    url.searchParams.set("machine", machine)
    
    const es = new EventSource(url.toString())
    es.onmessage = (e) => {
        if (e.data === "[DONE]") { es.close(); onDone(); return; }
        onChunk(e.data)
    }
    es.onerror = () => es.close()
    return () => es.close()
}

export const getMetrics = () =>
    fetch(`${BASE_URL}/api/mlops/metrics`).then(r => r.json())

export const getLog = (limit=50) =>
    fetch(`${BASE_URL}/api/log?limit=${limit}`).then(r => r.json())
