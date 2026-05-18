import React, { useState } from 'react'
import { Hexagon, LayoutDashboard, History, ScanSearch, Settings } from 'lucide-react'
import ImageUpload from './components/ImageUpload'
import CameraView from './components/CameraView'
import AgentPanel from './components/AgentPanel'
import MLOpsDashboard from './components/MLOpsDashboard'
import ProductionLog from './components/ProductionLog'
import { useInspection } from './hooks/useInspection'

function App() {
  const [activeTab, setActiveTab] = useState('inspect')
  const { state, file, setFile, preview, setPreview, result, agentSteps, runInspection } = useInspection()

  const handleInspect = () => {
    // In a real app, these might come from a dropdown or barcode scanner
    runInspection("Milling-CNC-04", "EngineBlock-V8")
  }

  return (
    <div className="flex h-screen overflow-hidden bg-bg">
      {/* Sidebar Navigation */}
      <nav className="w-16 border-r border-border bg-bg2 flex flex-col items-center py-6 z-20">
        <div className="w-10 h-10 bg-accent rounded-xl flex items-center justify-center mb-8 shadow-[0_0_15px_rgba(0,212,170,0.4)]">
          <Hexagon className="w-6 h-6 text-bg fill-current" />
        </div>
        
        <div className="flex flex-col gap-4 flex-1">
          <NavItem icon={<ScanSearch />} active={activeTab === 'inspect'} onClick={() => setActiveTab('inspect')} label="Inspect" />
          <NavItem icon={<LayoutDashboard />} active={activeTab === 'dashboard'} onClick={() => setActiveTab('dashboard')} label="MLOps" />
          <NavItem icon={<History />} active={activeTab === 'logs'} onClick={() => setActiveTab('logs')} label="Logs" />
        </div>
        
        <NavItem icon={<Settings />} onClick={() => {}} label="Settings" />
      </nav>

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto p-8">
        <header className="mb-8">
          <h1 className="text-2xl font-semibold tracking-tight text-text">FertigungsAI</h1>
          <p className="text-text3 text-sm mt-1">Multimodal AI Quality Control Inspector</p>
        </header>

        {activeTab === 'inspect' && (
          <div className="grid grid-cols-12 gap-8 h-[calc(100vh-140px)]">
            <div className="col-span-8 flex flex-col gap-6">
              <div className="h-2/3">
                <CameraView 
                    preview={preview} 
                    detections={result?.detections} 
                    status={state === 'uploading' ? 'scanning' : state} 
                />
              </div>
              <div className="h-1/3 flex gap-6">
                <div className="flex-1">
                  <ImageUpload file={file} setFile={setFile} preview={preview} setPreview={setPreview} />
                </div>
                <div className="w-48 flex items-center justify-center">
                  <button 
                    className={`w-full py-4 rounded-xl font-bold tracking-widest uppercase transition-all shadow-lg ${
                      file && state !== 'uploading' 
                        ? 'bg-accent text-bg hover:bg-[#00e6b8] shadow-accent/20 hover:shadow-accent/40 cursor-pointer' 
                        : 'bg-bg3 text-text3 cursor-not-allowed border border-border'
                    }`}
                    onClick={handleInspect}
                    disabled={!file || state === 'uploading'}
                  >
                    {state === 'uploading' ? 'Analyzing...' : 'Inspect'}
                  </button>
                </div>
              </div>
            </div>
            <div className="col-span-4 h-full overflow-y-auto pr-2 pb-8">
              <AgentPanel steps={agentSteps} result={result} />
            </div>
          </div>
        )}

        {activeTab === 'dashboard' && (
          <div className="max-w-6xl mx-auto">
            <h2 className="text-xl font-medium mb-6">MLOps & Telemetry Dashboard</h2>
            <MLOpsDashboard />
          </div>
        )}

        {activeTab === 'logs' && (
          <div className="max-w-6xl mx-auto">
            <h2 className="text-xl font-medium mb-6">Live Production Logs</h2>
            <ProductionLog />
          </div>
        )}
      </main>
    </div>
  )
}

function NavItem({ icon, active, onClick, label }) {
  return (
    <button 
      onClick={onClick}
      className={`relative group p-3 rounded-xl transition-all duration-200 ${
        active ? 'bg-accent/10 text-accent' : 'text-text3 hover:text-text hover:bg-bg3'
      }`}
      title={label}
    >
      {React.cloneElement(icon, { className: "w-5 h-5" })}
      {active && <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 bg-accent rounded-r-full" />}
      
      {/* Tooltip */}
      <div className="absolute left-full ml-4 px-2 py-1 bg-bg4 text-text text-xs rounded opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all whitespace-nowrap z-50">
        {label}
      </div>
    </button>
  )
}

export default App
