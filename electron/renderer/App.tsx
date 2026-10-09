import { lazy, Suspense, useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import ErrorBoundary from './components/ErrorBoundary'
import OnboardingModal from './components/OnboardingModal'
import ChatGPTWelcome from './components/ChatGPTWelcome'
import ReportIssueModal from './components/ReportIssueModal'
import UpdateDialog from './components/UpdateDialog'
import { useErrorReporter } from './hooks/useErrorReporter'
import { useAnnouncements } from './hooks/useAnnouncements'
import {
  DEFAULT_CHRONICLE_REFRESH_MODE,
  DEFAULT_MODEL_ROUTING_MODE,
  DEFAULT_LANGUAGE,
  DEFAULT_RESOLVED_LANGUAGE,
  DEFAULT_UI_THEME,
  normalizeChronicleRefreshMode,
  normalizeModelRoutingMode,
  normalizeResolvedLanguage,
  normalizeLanguage,
  normalizeUiTheme,
  type ChronicleRefreshMode,
  type ModelRoutingMode,
  type ResolvedLanguage,
  type LanguageSetting,
  type UiTheme,
} from './hooks/useSettings'
import { isRtlLanguage } from './i18n/languages'
import { loadLanguage } from './i18n'
import { AnnouncementPanel } from './components/AnnouncementPanel'
import { HUDContainer } from './components/hud/HUDContainer'
import { HUDNavBar } from './components/hud/HUDNavBar'
import { HUDStatusBar } from './components/hud/HUDStatusBar'
import { motionTiming } from './lib/motion'

import ChatPage from './pages/ChatPage'
const ChroniclePage = lazy(() => import('./pages/ChroniclePage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))

type Tab = 'chat' | 'chronicle' | 'settings'

// Shared transition for tab crossfade
const tabTransition = {
  duration: motionTiming.content,
  ease: [0.25, 0.46, 0.45, 0.94] as const,
}

function App() {
  const { t, i18n } = useTranslation()
  const [activeTab, setActiveTab] = useState<Tab>('chat')
  const [mountedTabs, setMountedTabs] = useState<Set<Tab>>(() => new Set(['chat']))
  useEffect(() => {
    setMountedTabs(previous => previous.has(activeTab) ? previous : new Set([...previous, activeTab]))
  }, [activeTab])
  useEffect(() => {
    // Chronicle owns chapter finalization while gameplay is in the foreground.
    // Activate that service on minimize even if the reader has not been opened.
    const ensureBackgroundChronicle = () => {
      if (document.visibilityState !== 'hidden') return
      setMountedTabs(previous => previous.has('chronicle') ? previous : new Set([...previous, 'chronicle']))
    }
    ensureBackgroundChronicle()
    document.addEventListener('visibilitychange', ensureBackgroundChronicle)
    return () => document.removeEventListener('visibilitychange', ensureBackgroundChronicle)
  }, [])
  const [settingsTarget, setSettingsTarget] = useState({ id: 'ai-setup', request: 0 })
  const openAISetup = (id = 'ai-setup') => {
    setSettingsTarget(current => ({ id, request: current.request + 1 }))
    setActiveTab('settings')
  }
  const [campaignHistoryOpenRequest, setCampaignHistoryOpenRequest] = useState(0)
  const [uiTheme, setUiTheme] = useState<UiTheme>(DEFAULT_UI_THEME)
  const [chronicleRefreshMode, setChronicleRefreshMode] = useState<ChronicleRefreshMode>(
    DEFAULT_CHRONICLE_REFRESH_MODE,
  )
  const [modelRoutingMode, setModelRoutingMode] = useState<ModelRoutingMode>(
    DEFAULT_MODEL_ROUTING_MODE,
  )
  const [resolvedLanguage, setResolvedLanguage] = useState<ResolvedLanguage>(
    DEFAULT_RESOLVED_LANGUAGE,
  )
  const [language, setLanguage] = useState<LanguageSetting>(DEFAULT_LANGUAGE)
  const [languageReady, setLanguageReady] = useState(false)
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
    const timeout = new Promise<never>((_, reject) => {
      setTimeout(() => reject(new Error('Settings load timed out')), 5000)
    })
    Promise.race([window.electronAPI?.getSettings() ?? Promise.reject(new Error('Electron API unavailable')), timeout]).then(async (settings) => {
      const loadedSettings = settings as {
        uiTheme?: unknown
        chronicleRefreshMode?: unknown
        modelRoutingMode?: unknown
        resolvedLanguage?: unknown
        language?: unknown
      }
      const loadedTheme = normalizeUiTheme(loadedSettings?.uiTheme)
      const loadedChronicleRefreshMode = normalizeChronicleRefreshMode(
        loadedSettings?.chronicleRefreshMode,
      )
      const loadedModelRoutingMode = normalizeModelRoutingMode(loadedSettings?.modelRoutingMode)
      let loadedResolvedLanguage = normalizeResolvedLanguage(loadedSettings?.resolvedLanguage)
      try {
        await loadLanguage(loadedResolvedLanguage)
      } catch {
        // A damaged catalog must not strand the application behind a blank window.
        loadedResolvedLanguage = DEFAULT_RESOLVED_LANGUAGE
      }
      await i18n.changeLanguage(loadedResolvedLanguage)
      document.documentElement.lang = loadedResolvedLanguage
      setUiTheme(loadedTheme)
      setChronicleRefreshMode(loadedChronicleRefreshMode)
      setModelRoutingMode(loadedModelRoutingMode)
      setResolvedLanguage(loadedResolvedLanguage)
      setLanguage(normalizeLanguage(loadedSettings?.language))
    }).catch(() => {
      // A failed settings read must not strand first-run users behind a blank window.
    }).finally(() => {
      setLanguageReady(true)
    })
  }, [i18n])

  const changeLanguage = useCallback(async (nextLanguage: LanguageSetting): Promise<boolean> => {
    if (!window.electronAPI) return false
    let persisted = false
    try {
      if (nextLanguage !== 'system') await loadLanguage(nextLanguage)
      const result = await window.electronAPI.saveSettings({ language: nextLanguage })
      if (result?.success === false) return false
      persisted = true
      const resolved = normalizeResolvedLanguage(result.resolvedLanguage)
      await loadLanguage(resolved)
      await i18n.changeLanguage(resolved)
      setLanguage(normalizeLanguage(result.language))
      setResolvedLanguage(resolved)
      return true
    } catch {
      // System-default is resolved by the main process. Restore the previous
      // preference if its catalog could not be loaded after that resolution.
      if (persisted) {
        try { await window.electronAPI.saveSettings({ language }) } catch { /* The selector reports the failed change. */ }
      }
      return false
    }
  }, [i18n, language])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', uiTheme)
  }, [uiTheme])

  useEffect(() => {
    document.documentElement.lang = resolvedLanguage
    document.documentElement.dir = isRtlLanguage(resolvedLanguage) ? 'rtl' : 'ltr'
  }, [resolvedLanguage])

  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: 'chat', label: t('app.tabs.chat'), icon: '◈' },
    { id: 'chronicle', label: t('app.tabs.chronicle'), icon: '◇' },
    { id: 'settings', label: t('app.tabs.settings'), icon: '⚙' },
  ]

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
    if (!languageReady || onboardingDone !== true || announcementsLoading
      || unreadCount <= 0 || didAutoOpenTransmissionsRef.current) return

    didAutoOpenTransmissionsRef.current = true
    setTransmissionsOpen(true)
  }, [hasTransmissions, languageReady, onboardingDone, announcementsLoading, unreadCount])

  // Only acknowledge IDs after their panel has rendered in the ready app.
  useEffect(() => {
    if (transmissionsOpen && languageReady && onboardingDone === true
      && !announcementsLoading && unreadCount > 0) markAllRead()
  }, [transmissionsOpen, languageReady, onboardingDone, announcementsLoading, unreadCount, markAllRead])

  const handleToggleTransmissions = useCallback(() => {
    setTransmissionsOpen((prev) => !prev)
  }, [])

  const handleCloseTransmissions = useCallback(() => {
    setTransmissionsOpen(false)
  }, [])

  const handleOpenCampaignHistory = useCallback(() => {
    setActiveTab('chronicle')
    setCampaignHistoryOpenRequest(request => request + 1)
  }, [])

  if (!languageReady || onboardingDone === null) return null

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
        <div className="app-navigation flex-none pt-2 pb-2">
            <HUDNavBar
              tabs={tabs}
              activeTab={activeTab}
              onTabChange={(id) => setActiveTab(id as Tab)}
            />
        </div>

        <AnnouncementPanel
          announcements={announcements}
          unreadCount={unreadCount}
          isOpen={transmissionsOpen}
          onClose={handleCloseTransmissions}
          onDismiss={dismissAnnouncement}
          onDismissAll={dismissAllAnnouncements}
          onMarkRead={markAllRead}
        />

        {/* Main Content Area */}
        <main className="flex-1 min-h-0 relative overflow-hidden">
            {(['chat', 'chronicle', 'settings'] as const).map((tab) => {
              const isActive = activeTab === tab
              return (
                <motion.div
                  key={tab}
                  id={`page-${tab}`}
                  data-active={isActive}
                  className="app-page absolute inset-0 px-4 pb-4 min-h-0 overflow-hidden"
                  initial={false}
                  animate={{
                    opacity: isActive ? 1 : 0,
                  }}
                  transition={tabTransition}
                  style={{
                    pointerEvents: isActive ? 'auto' : 'none',
                    zIndex: isActive ? 1 : 0,
                  }}
                  // React 18 forwards inert as a string attribute, not a boolean.
                  // @ts-expect-error framer-motion types do not include inert yet
                  inert={isActive ? undefined : ''}
                  aria-hidden={!isActive}
                >
                  <div className="h-full w-full">
                    <Suspense fallback={<div role="status" className="p-6 text-text-secondary">{t('common.loading')}</div>}>
                    {tab === 'chat' && (
                      <ChatPage
                        isActive={isActive}
                        modelRoutingMode={modelRoutingMode}
                        onOpenSettings={() => openAISetup()}
                        onOpenSaveSettings={() => openAISetup('save-data')}
                        onReportLlmIssue={openLLMReportModal}
                      />
                    )}
                    {tab === 'chronicle' && (isActive || mountedTabs.has(tab)) && (
                      <ChroniclePage
                        isActive={isActive}
                        refreshMode={chronicleRefreshMode}
                        modelRoutingMode={modelRoutingMode}
                        onOpenSettings={() => openAISetup()}
                        historyOpenRequest={campaignHistoryOpenRequest}
                      />
                    )}
                    {tab === 'settings' && (isActive || mountedTabs.has(tab)) && (
                      <SettingsPage
                        isActive={isActive}
                        openTarget={settingsTarget}
                        key={onboardingDone ? 'post-onboarding' : 'pre-onboarding'}
                        onReportIssue={openReportModal}
                        onThemeChange={setUiTheme}
                        onChronicleRefreshModeChange={setChronicleRefreshMode}
                        onModelRoutingModeChange={setModelRoutingMode}
                        onLanguageSelect={changeLanguage}
                        onOpenCampaignHistory={handleOpenCampaignHistory}
                      />
                    )}
                    </Suspense>
                  </div>
                </motion.div>
              )
            })}
        </main>
      </HUDContainer>

      {/* Onboarding Modal */}
      <AnimatePresence>
        {onboardingDone === false && (
          <OnboardingModal
            onComplete={openAIApps => {
              setOnboardingDone(true)
              if (openAIApps) openAISetup('ai-app-connections')
            }}
            language={language}
            onLanguageSelect={changeLanguage}
          />
        )}
      </AnimatePresence>

      {/* Report Issue Modal */}
      <ChatGPTWelcome enabled={onboardingDone === true} />
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
