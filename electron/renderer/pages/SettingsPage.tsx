// SettingsPage - UI-004
// Implements settings management for API keys, save path, and Discord integration

import { useState, useEffect, useRef } from 'react'
import { useSettings } from '../hooks/useSettings'

function SettingsPage() {
  const { settings, loading, saving, error, saveSettings, showFolderDialog } = useSettings()

  // Form state - separate from saved settings to allow editing before save
  const [googleApiKey, setGoogleApiKey] = useState('')
  const [savePath, setSavePath] = useState('')
  const [discordEnabled, setDiscordEnabled] = useState(false)
  const [discordToken, setDiscordToken] = useState('')

  // Track if form has unsaved changes
  const [hasChanges, setHasChanges] = useState(false)

  // Track successful save for feedback
  const [saveSuccess, setSaveSuccess] = useState(false)

  // Ref for success message timeout to allow cleanup
  const successTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Cleanup timeout on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (successTimeoutRef.current) {
        clearTimeout(successTimeoutRef.current)
      }
    }
  }, [])

  // Initialize form when settings load
  useEffect(() => {
    if (settings) {
      // For secrets, show the masked value (or empty if not set)
      setGoogleApiKey(settings.googleApiKeySet ? settings.googleApiKey : '')
      setDiscordToken(settings.discordTokenSet ? settings.discordToken : '')
      setSavePath(settings.savePath || '')
      setDiscordEnabled(settings.discordEnabled)
    }
  }, [settings])

  // Track changes
  useEffect(() => {
    if (!settings) return

    const hasApiKeyChange = settings.googleApiKeySet
      ? googleApiKey !== settings.googleApiKey
      : googleApiKey !== ''
    const hasTokenChange = settings.discordTokenSet
      ? discordToken !== settings.discordToken
      : discordToken !== ''
    const hasPathChange = savePath !== (settings.savePath || '')
    const hasDiscordChange = discordEnabled !== settings.discordEnabled

    setHasChanges(hasApiKeyChange || hasTokenChange || hasPathChange || hasDiscordChange)
  }, [googleApiKey, discordToken, savePath, discordEnabled, settings])

  const handleBrowse = async () => {
    const selectedPath = await showFolderDialog()
    if (selectedPath) {
      setSavePath(selectedPath)
    }
  }

  const handleSave = async () => {
    setSaveSuccess(false)

    // Build the settings object to save
    // Only include secrets if they've been modified (not masked values)
    const settingsToSave: Record<string, string | boolean> = {
      savePath,
      discordEnabled,
    }

    // Only save API key if it's a new value (doesn't contain mask pattern)
    if (!googleApiKey.includes('...')) {
      settingsToSave.googleApiKey = googleApiKey
    }

    // Only save Discord token if it's a new value (doesn't contain mask pattern)
    if (!discordToken.includes('...')) {
      settingsToSave.discordToken = discordToken
    }

    const success = await saveSettings(settingsToSave)
    if (success) {
      setSaveSuccess(true)
      setHasChanges(false)
      // Clear any existing timeout before setting a new one
      if (successTimeoutRef.current) {
        clearTimeout(successTimeoutRef.current)
      }
      // Clear success message after 3 seconds
      successTimeoutRef.current = setTimeout(() => setSaveSuccess(false), 3000)
    }
  }

  // Check if this is first run (no API key configured)
  const isFirstRun = settings && !settings.googleApiKeySet

  if (loading) {
    return (
      <div className="settings-page">
        <div className="settings-loading">Loading settings...</div>
      </div>
    )
  }

  return (
    <div className="settings-page">
      <div className="settings-container">
        <h1 className="settings-title">Settings</h1>

        {/* First-run welcome message */}
        {isFirstRun && (
          <div className="settings-welcome">
            <h2>Welcome to Stellaris Companion</h2>
            <p>
              To get started, you'll need to configure a Google API key for the Gemini AI model.
              This key is stored securely on your device and never shared.
            </p>
          </div>
        )}

        {/* Error display */}
        {error && (
          <div className="settings-error">
            {error}
          </div>
        )}

        {/* Success message */}
        {saveSuccess && (
          <div className="settings-success">
            Settings saved successfully. Backend is restarting...
          </div>
        )}

        {/* API Configuration Section */}
        <section className="settings-section">
          <h2 className="section-title">API Configuration</h2>
          <div className="settings-card">
            <div className="form-group">
              <label htmlFor="google-api-key">
                Google API Key (Gemini)
                {settings?.googleApiKeySet && (
                  <span className="key-status key-set"> (configured)</span>
                )}
                {settings && !settings.googleApiKeySet && (
                  <span className="key-status key-not-set"> (not set)</span>
                )}
              </label>
              <input
                id="google-api-key"
                type="password"
                value={googleApiKey}
                onChange={(e) => setGoogleApiKey(e.target.value)}
                placeholder={settings?.googleApiKeySet ? 'Enter new key to replace' : 'Enter your Google API key'}
                className="form-input"
              />
              <p className="form-help">
                Get a key at{' '}
                <a
                  href="https://aistudio.google.com/app/apikey"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="form-link"
                >
                  Google AI Studio
                </a>
              </p>
            </div>
          </div>
        </section>

        {/* Save File Location Section */}
        <section className="settings-section">
          <h2 className="section-title">Save File Location</h2>
          <div className="settings-card">
            <div className="form-group">
              <label htmlFor="save-path">Stellaris Save Folder</label>
              <div className="input-with-button">
                <input
                  id="save-path"
                  type="text"
                  value={savePath}
                  onChange={(e) => setSavePath(e.target.value)}
                  placeholder="Leave empty to auto-detect"
                  className="form-input"
                  readOnly
                />
                <button
                  type="button"
                  onClick={handleBrowse}
                  className="browse-button"
                >
                  Browse...
                </button>
              </div>
              <p className="form-help">
                Leave empty to auto-detect the default Stellaris save location.
              </p>
            </div>
          </div>
        </section>

        {/* Discord Bot Section */}
        <section className="settings-section">
          <h2 className="section-title">Discord Bot (Optional)</h2>
          <div className="settings-card">
            <div className="form-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={discordEnabled}
                  onChange={(e) => setDiscordEnabled(e.target.checked)}
                  className="form-checkbox"
                />
                <span>Enable Discord bot</span>
              </label>
            </div>

            {/* Conditional Discord token input */}
            {discordEnabled && (
              <div className="form-group">
                <label htmlFor="discord-token">
                  Discord Bot Token
                  {settings?.discordTokenSet && (
                    <span className="key-status key-set"> (configured)</span>
                  )}
                  {settings && !settings.discordTokenSet && (
                    <span className="key-status key-not-set"> (not set)</span>
                  )}
                </label>
                <input
                  id="discord-token"
                  type="password"
                  value={discordToken}
                  onChange={(e) => setDiscordToken(e.target.value)}
                  placeholder={settings?.discordTokenSet ? 'Enter new token to replace' : 'Enter your Discord bot token'}
                  className="form-input"
                />
                <p className="form-help">
                  Create a bot at the{' '}
                  <a
                    href="https://discord.com/developers/applications"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="form-link"
                  >
                    Discord Developer Portal
                  </a>
                </p>
              </div>
            )}
          </div>
        </section>

        {/* Save Button */}
        <div className="settings-actions">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !hasChanges}
            className="save-button"
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
          {hasChanges && (
            <span className="unsaved-indicator">You have unsaved changes</span>
          )}
        </div>
      </div>
    </div>
  )
}

export default SettingsPage
