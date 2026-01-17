import { useState, useEffect } from 'react'

interface Settings {
  googleApiKey: string
  discordToken: string
  savePath: string
  discordEnabled: boolean
}

export function useSettings() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadSettings = async () => {
      if (window.electronAPI) {
        const loaded = await window.electronAPI.getSettings() as Settings
        setSettings(loaded)
      }
      setLoading(false)
    }
    loadSettings()
  }, [])

  const saveSettings = async (newSettings: Partial<Settings>) => {
    if (window.electronAPI) {
      await window.electronAPI.saveSettings(newSettings)
      setSettings((prev) => prev ? { ...prev, ...newSettings } : null)
    }
  }

  return { settings, loading, saveSettings }
}

export default useSettings
