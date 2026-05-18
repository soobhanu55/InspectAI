import { useState, useCallback, useRef } from 'react'
import { streamChat } from '../lib/api'

export function useSSEStream() {
    const [messages, setMessages] = useState([])
    const [isStreaming, setIsStreaming] = useState(false)
    const sessionIdRef = useRef(Math.random().toString(36).substring(7))
    
    const sendMessage = useCallback((query, machine) => {
        if (!query.trim()) return
        
        setMessages(prev => [...prev, { role: 'user', content: query }])
        setMessages(prev => [...prev, { role: 'assistant', content: '' }])
        setIsStreaming(true)
        
        streamChat(
            query,
            sessionIdRef.current,
            machine,
            (chunk) => {
                setMessages(prev => {
                    const newMsgs = [...prev]
                    newMsgs[newMsgs.length - 1].content += chunk
                    return newMsgs
                })
            },
            () => {
                setIsStreaming(false)
            }
        )
    }, [])
    
    return { messages, isStreaming, sendMessage }
}
