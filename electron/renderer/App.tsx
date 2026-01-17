import { useState } from 'react'
import ChatPage from './pages/ChatPage'
import RecapPage from './pages/RecapPage'
import SettingsPage from './pages/SettingsPage'
import StatusBar from './components/StatusBar'

type Tab = 'chat' | 'recap' | 'settings'

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('chat')

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
          className={activeTab === 'recap' ? 'active' : ''}
          onClick={() => setActiveTab('recap')}
        >
          Recap
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
        {activeTab === 'recap' && <RecapPage />}
        {activeTab === 'settings' && <SettingsPage />}
      </main>
    </div>
  )
}

export default App
