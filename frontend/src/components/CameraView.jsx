import React, { useEffect, useRef } from 'react'

export default function CameraView({ preview, detections, status }) {
    const canvasRef = useRef(null)

    useEffect(() => {
        if (!preview) return
        
        const canvas = canvasRef.current
        const ctx = canvas.getContext('2d')
        const img = new Image()
        
        img.onload = () => {
            canvas.width = img.width
            canvas.height = img.height
            ctx.drawImage(img, 0, 0)
            
            if (detections && detections.length > 0) {
                detections.forEach(d => {
                    const { x, y, w, h } = d.bbox
                    
                    // Determine color based on severity
                    let color = '#00d4aa' // accent (low/none)
                    if (d.severity === 'high') color = '#ff3b5c' // danger
                    else if (d.severity === 'medium') color = '#ff9500' // warn
                    
                    // Draw bounding box
                    ctx.strokeStyle = color
                    ctx.lineWidth = 3
                    ctx.setLineDash([8, 4])
                    ctx.strokeRect(x, y, w, h)
                    ctx.setLineDash([])
                    
                    // Draw corners (L-markers)
                    const len = 15
                    ctx.beginPath()
                    // Top-left
                    ctx.moveTo(x, y + len)
                    ctx.lineTo(x, y)
                    ctx.lineTo(x + len, y)
                    // Top-right
                    ctx.moveTo(x + w - len, y)
                    ctx.lineTo(x + w, y)
                    ctx.lineTo(x + w, y + len)
                    // Bottom-right
                    ctx.moveTo(x + w, y + h - len)
                    ctx.lineTo(x + w, y + h)
                    ctx.lineTo(x + w - len, y + h)
                    // Bottom-left
                    ctx.moveTo(x + len, y + h)
                    ctx.lineTo(x, y + h)
                    ctx.lineTo(x, y + h - len)
                    ctx.stroke()
                    
                    // Draw Label Badge
                    const labelText = `${d.class_name.toUpperCase()} ${(d.confidence * 100).toFixed(0)}%`
                    ctx.font = '14px "JetBrains Mono", monospace'
                    const textWidth = ctx.measureText(labelText).width
                    
                    ctx.fillStyle = color
                    ctx.fillRect(x, y - 24, textWidth + 12, 24)
                    
                    ctx.fillStyle = '#0a0c0f' // dark bg for text
                    ctx.fillText(labelText, x + 6, y - 7)
                })
            }
        }
        img.src = preview
    }, [preview, detections])

    if (!preview) {
        return (
            <div className="w-full h-full min-h-[400px] flex items-center justify-center bg-bg2/50 border border-border rounded-xl">
                <span className="text-text3 font-mono text-sm uppercase tracking-widest">
                    [ No Image Data ]
                </span>
            </div>
        )
    }

    return (
        <div className="relative w-full h-full rounded-xl overflow-hidden glass-panel group">
            <div className="w-full h-full flex items-center justify-center bg-black">
                <canvas 
                    ref={canvasRef} 
                    className="max-w-full max-h-[500px] object-contain"
                />
            </div>
            
            {/* Scanning Animation overlay */}
            {status === 'scanning' && (
                <div className="absolute inset-0 overflow-hidden pointer-events-none">
                    <div className="w-full h-[2px] bg-accent/80 shadow-[0_0_10px_#00d4aa] absolute animate-[scan_2s_ease-in-out_infinite]" />
                    <div className="absolute inset-0 bg-accent/5 animate-[pulse_2s_ease-in-out_infinite]" />
                </div>
            )}
            
            {/* HUD */}
            <div className="absolute top-4 left-4 flex gap-2">
                <span className="px-2 py-1 bg-black/60 backdrop-blur border border-white/10 rounded text-xs font-mono text-accent">
                    LIVE
                </span>
                {status === 'complete' && detections?.length > 0 && (
                    <span className="px-2 py-1 bg-danger/20 backdrop-blur border border-danger/50 rounded text-xs font-mono text-danger animate-pulse">
                        DEFECT DETECTED
                    </span>
                )}
            </div>
            
            <div className="absolute bottom-4 left-4 text-xs font-mono text-white/50 bg-black/60 px-2 py-1 rounded backdrop-blur">
                CAM_01_INSPECT
            </div>
            <div className="absolute bottom-4 right-4 text-xs font-mono text-white/50 bg-black/60 px-2 py-1 rounded backdrop-blur">
                {new Date().toISOString().split('T')[1].slice(0,8)}
            </div>

            <style>{`
                @keyframes scan {
                    0% { top: 0; }
                    50% { top: 100%; }
                    100% { top: 0; }
                }
            `}</style>
        </div>
    )
}
