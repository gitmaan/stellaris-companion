/**
 * Fetch available models from an Ollama server.
 * @param {string} baseUrl - The Ollama server base URL (e.g., http://localhost:11434)
 * @returns {Promise<{models: Array<{name: string, size: number, modifiedAt: string}>, error?: string}>}
 */
async function fetchOllamaModels(baseUrl) {
  try {
    const url = new URL('/api/tags', baseUrl)
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 5000) // 5 second timeout
    
    const response = await fetch(url.toString(), {
      method: 'GET',
      signal: controller.signal,
    })
    clearTimeout(timeout)
    
    if (!response.ok) {
      return { models: [], error: `Ollama returned status ${response.status}` }
    }
    
    const data = await response.json()
    // Ollama returns { models: [{ name, size, modified_at, ... }] }
    const models = (data.models || []).map(m => ({
      name: m.name,
      size: m.size,
      modifiedAt: m.modified_at,
    }))
    
    return { models }
  } catch (err) {
    if (err.name === 'AbortError') {
      return { models: [], error: 'Connection timed out' }
    }
    return { models: [], error: err.message || 'Failed to connect to Ollama' }
  }
}

function registerSettingsIpcHandlers({
  ipcMain,
  validateSender,
  dialog,
  getMainWindow,
  getSettings,
  saveSettings,
  getSettingsWithSecrets,
  onSettingsSaved,
}) {
  ipcMain.handle('load-settings', async (event) => {
    validateSender(event)
    return getSettings()
  })

  ipcMain.handle('save-settings', async (event, settings) => {
    validateSender(event)
    await saveSettings(settings)

    const fullSettings = await getSettingsWithSecrets()
    await onSettingsSaved(fullSettings, settings || {})

    return { success: true }
  })

  ipcMain.handle('select-folder', async (event) => {
    validateSender(event)
    const result = await dialog.showOpenDialog(getMainWindow(), {
      properties: ['openDirectory'],
      title: 'Select Stellaris Save Folder',
    })

    if (result.canceled || !result.filePaths.length) {
      return null
    }

    return result.filePaths[0]
  })

  // Fetch available models from Ollama server
  ipcMain.handle('fetch-ollama-models', async (event, { baseUrl }) => {
    validateSender(event)
    if (!baseUrl) {
      return { models: [], error: 'No base URL provided' }
    }
    return fetchOllamaModels(baseUrl)
  })
}

module.exports = {
  registerSettingsIpcHandlers,
}
