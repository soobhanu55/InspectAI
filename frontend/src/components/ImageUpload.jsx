import React, { useCallback, useState } from 'react'
import { UploadCloud, X, Image as ImageIcon } from 'lucide-react'

export default function ImageUpload({ file, setFile, preview, setPreview }) {
    const [isDragging, setIsDragging] = useState(false)

    const handleFile = (selectedFile) => {
        if (!selectedFile || !selectedFile.type.startsWith('image/')) {
            alert("Please upload a valid image file.")
            return
        }
        if (selectedFile.size > 10 * 1024 * 1024) {
            alert("File size exceeds 10MB limit.")
            return
        }
        setFile(selectedFile)
        const reader = new FileReader()
        reader.onloadend = () => {
            setPreview(reader.result)
        }
        reader.readAsDataURL(selectedFile)
    }

    const onDrop = useCallback(e => {
        e.preventDefault()
        setIsDragging(false)
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleFile(e.dataTransfer.files[0])
            e.dataTransfer.clearData()
        }
    }, [])

    const onDragOver = useCallback(e => {
        e.preventDefault()
        setIsDragging(true)
    }, [])

    const onDragLeave = useCallback(e => {
        e.preventDefault()
        setIsDragging(false)
    }, [])

    if (preview) {
        return (
            <div className="relative rounded-xl overflow-hidden glass-panel group">
                <img src={preview} alt="Preview" className="w-full h-auto object-cover max-h-[400px]" />
                <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <button 
                        onClick={() => { setFile(null); setPreview(null) }}
                        className="bg-danger/80 text-white p-3 rounded-full hover:bg-danger transition-colors"
                    >
                        <X className="w-6 h-6" />
                    </button>
                </div>
                <div className="absolute bottom-0 left-0 right-0 p-3 bg-gradient-to-t from-black/80 to-transparent flex justify-between items-center text-sm">
                    <div className="flex items-center gap-2">
                        <ImageIcon className="w-4 h-4 text-accent" />
                        <span className="text-gray-200 truncate max-w-[200px]">{file?.name}</span>
                    </div>
                    <span className="text-gray-400">{(file?.size / 1024 / 1024).toFixed(2)} MB</span>
                </div>
            </div>
        )
    }

    return (
        <div 
            onDrop={onDrop}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            className={`
                border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-300
                flex flex-col items-center justify-center min-h-[300px]
                ${isDragging ? 'border-accent bg-accent/5 scale-[1.02]' : 'border-border bg-bg2 hover:border-text3 hover:bg-bg3'}
            `}
            onClick={() => document.getElementById('file-upload').click()}
        >
            <div className={`
                p-4 rounded-full mb-4 transition-colors
                ${isDragging ? 'bg-accent/20 text-accent' : 'bg-bg4 text-text2'}
            `}>
                <UploadCloud className="w-8 h-8" />
            </div>
            <h3 className="text-lg font-medium text-text mb-2">Drop image here or click to browse</h3>
            <p className="text-sm text-text3 max-w-sm">
                Supports JPG, PNG up to 10MB.<br/>
                Must be at least 64x64 pixels.
            </p>
            <input 
                id="file-upload" 
                type="file" 
                accept="image/*" 
                className="hidden" 
                onChange={(e) => {
                    if (e.target.files && e.target.files.length > 0) {
                        handleFile(e.target.files[0])
                    }
                }}
            />
        </div>
    )
}
