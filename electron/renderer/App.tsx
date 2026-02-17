import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ErrorBoundary from './components/ErrorBoundary'
import OnboardingModal from './components/OnboardingModal'
import ReportIssueModal from './components/ReportIssueModal'
import UpdateDialog from './components/UpdateDialog'
import { useErrorReporter } from './hooks/useErrorReporter'
import { useAnnouncements } from './hooks/useAnnouncements'
import { DEFAULT_UI_THEME, normalizeUiTheme, type UiTheme } from './hooks/useSettings'
import { AnnouncementPanel } from './components/AnnouncementPanel'
import { HUDContainer } from './components/hud/HUDContainer'
import { HUDNavBar } from './components/hud/HUDNavBar'
import { HUDStatusBar } from './components/hud/HUDStatusBar'

// Direct imports
import ChatPage from './pages/ChatPage'
import ChroniclePage from './pages/ChroniclePage'
import SettingsPage from './pages/SettingsPage'

type Tab = 'chat' | 'chronicle' | 'settings'

const tabs: { id: Tab; label: string; icon: string }[] = [
  { id: 'chat', label: 'Advisor', icon: '◈' },
  { id: 'chronicle', label: 'Chronicle', icon: '◇' },
  { id: 'settings', label: 'Config', icon: '⚙' },
]

// Shared transition for tab crossfade
const tabTransition = {
  duration: 0.3,
  ease: [0.25, 0.46, 0.45, 0.94] as const,
}

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('chat')
  const [uiTheme, setUiTheme] = useState<UiTheme>(DEFAULT_UI_THEME)
  // Onboarding: null = checking, true = done, false = show modal
  const [onboardingDone, setOnboardingDone] = useState<boolean | null>(null)

  useEffect(() => {
    window.electronAPI?.onboarding.getStatus().then((done) => {
      setOnboardingDone(!!done)
    }).catch(() => {
      setOnboardingDone(true) // If check fails, skip onboarding
    })
  }, [])

  useEffect(() => {
    window.electronAPI?.getSettings().then((settings) => {
      const loadedTheme = normalizeUiTheme((settings as { uiTheme?: unknown })?.uiTheme)
      setUiTheme(loadedTheme)
    }).catch(() => {
      // Keep default theme when settings can't be loaded.
    })
  }, [])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', uiTheme)
  }, [uiTheme])

  // Error reporting
  const {
    promptErrorReport,
    openLLMReportModal,
    openReportModal,
    modalOpen,
    modalPrefill,
    closeModal,
  } = useErrorReporter()

  // Announcements
  const {
    announcements,
    unreadCount,
    loading: announcementsLoading,
    dismissAnnouncement,
    dismissAllAnnouncements,
    markAllRead,
  } = useAnnouncements()

  const totalTransmissions = announcements.length
  const hasTransmissions = totalTransmissions > 0
  const [transmissionsOpen, setTransmissionsOpen] = useState(false)
  const didAutoOpenTransmissionsRef = useRef(false)

  // Set platform class on body for platform-specific styling
  useEffect(() => {
    const isMac = navigator.platform.toLowerCase().includes('mac')
    document.body.classList.add(isMac ? 'platform-mac' : 'platform-win')
  }, [])

  useEffect(() => {
    if (!hasTransmissions) {
      setTransmissionsOpen(false)
      return
    }
    if (announcementsLoading || unreadCount <= 0 || didAutoOpenTransmissionsRef.current) return

    didAutoOpenTransmissionsRef.current = true
    setTransmissionsOpen(true)
    markAllRead()
  }, [hasTransmissions, announcementsLoading, unreadCount, markAllRead])

  const handleToggleTransmissions = useCallback(() => {
    setTransmissionsOpen((prev) => {
      const next = !prev
      if (next && unreadCount > 0) {
        markAllRead()
      }
      return next
    })
  }, [unreadCount, markAllRead])

  const handleCloseTransmissions = useCallback(() => {
    setTransmissionsOpen(false)
  }, [])

  return (
    <ErrorBoundary onError={(err) => promptErrorReport(err, 'ui')}>
      <HUDContainer data-theme={uiTheme} className="flex flex-col h-screen">
        {/* Top Status Bar - Fixed */}
        <div className="flex-none">
            <HUDStatusBar
              transmissionsOpen={transmissionsOpen}
              transmissionsTotal={totalTransmissions}
              transmissionsUnread={unreadCount}
              onToggleTransmissions={hasTransmissions ? handleToggleTransmissions : undefined}
            />
        </div>

        {/* Floating Navigation */}
        <div className="flex-none pt-2 pb-2">
            <HUDNavBar
              tabs={tabs}
              activeTab={activeTab}
              onTabChange={(id) => setActiveTab(id as Tab)}
            />
        </div>

        {/* Transmissions backdrop */}
        <AnimatePresence>
          {hasTransmissions && transmissionsOpen && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="absolute inset-0 z-[70]"
            >
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="absolute inset-0 bg-gradient-to-l from-black/45 via-black/30 to-black/20"
                onClick={handleCloseTransmissions}
              />
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.22 }}
                className="absolute inset-0 pointer-events-none bg-gradient-to-l from-black/12 via-black/8 to-black/5 backdrop-blur-[2px]"
              />
            </motion.div>
          )}
        </AnimatePresence>

        {hasTransmissions && (
          <div className="absolute right-6 top-14 z-[85] w-[min(34rem,calc(100%-3rem))] pointer-events-none">
            <div className="pointer-events-auto">
              <AnnouncementPanel
                announcements={announcements}
                unreadCount={unreadCount}
                isOpen={transmissionsOpen}
                onClose={handleCloseTransmissions}
                onDismiss={dismissAnnouncement}
                onDismissAll={dismissAllAnnouncements}
                onMarkRead={markAllRead}
              />
            </div>
          </div>
        )}

        {/* Main Content Area */}
        <main className="flex-1 relative overflow-hidden px-6 pb-6">
            {(['chat', 'chronicle', 'settings'] as const).map((tab) => {
              const isActive = activeTab === tab
              return (
                <motion.div
                  key={tab}
                  className={`absolute inset-0 px-6 pb-6 ${
                    tab === 'chat' ? 'overflow-hidden' : 'overflow-y-auto custom-scrollbar'
                  }`}
                  animate={{
                    opacity: isActive ? 1 : 0,
                    scale: isActive ? 1 : 0.98,
                  }}
                  transition={tabTransition}
                  style={{
                    pointerEvents: isActive ? 'auto' : 'none',
                    zIndex: isActive ? 1 : 0,
                  }}
                  // @ts-expect-error inert is valid HTML; framer-motion types lag
                  inert={!isActive || undefined}
                >
                  <div className="h-full w-full">
                    {tab === 'chat' && (
                      <ChatPage
                        isActive={isActive}
                        onReportLlmIssue={openLLMReportModal}
                      />
                    )}
                    {tab === 'chronicle' && <ChroniclePage />}
                    {tab === 'settings' && (
                      <SettingsPage
                        key={onboardingDone ? 'post-onboarding' : 'pre-onboarding'}
                        onReportIssue={openReportModal}
                        onThemeChange={setUiTheme}
                      />
                    )}
                  </div>
                </motion.div>
              )
            })}
        </main>
      </HUDContainer>

      {/* Onboarding Modal */}
      <AnimatePresence>
        {onboardingDone === false && (
          <OnboardingModal onComplete={() => setOnboardingDone(true)} />
        )}
      </AnimatePresence>

      {/* Report Issue Modal */}
      <ReportIssueModal
        isOpen={modalOpen}
        onClose={closeModal}
        prefill={modalPrefill || undefined}
      />

      {/* Update Dialog */}
      <UpdateDialog />
    </ErrorBoundary>
  )
}

export default App
