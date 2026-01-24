import { useState, useEffect } from 'react'
import ChatPage from './pages/ChatPage'
import ChroniclePage from './pages/ChroniclePage'
import SettingsPage from './pages/SettingsPage'
import StatusBar from './components/StatusBar'

type Tab = 'chat' | 'chronicle' | 'settings'

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('chat')

  // Set platform class on body for platform-specific styling
  useEffect(() => {
    const isMac = navigator.platform.toLowerCase().includes('mac')
    document.body.classList.add(isMac ? 'platform-mac' : 'platform-win')
  }, [])

  return (
    <div className="app">
      <StatusBar />
      <nav className="tab-nav">
        <button
          className={activeTab === 'chat' ? 'active' : ''}
          onClick={() => setActiveTab('chat')}
        >
          Chat
        </button>
        <button
          className={activeTab === 'chronicle' ? 'active' : ''}
          onClick={() => setActiveTab('chronicle')}
        >
          Chronicle
        </button>
        <button
          className={activeTab === 'settings' ? 'active' : ''}
          onClick={() => setActiveTab('settings')}
        >
          Settings
        </button>
      </nav>
      <main className="main-content">
        {activeTab === 'chat' && <ChatPage />}
        {activeTab === 'chronicle' && <ChroniclePage />}
        {activeTab === 'settings' && <SettingsPage />}
      </main>
    </div>
  )
}

export default App
