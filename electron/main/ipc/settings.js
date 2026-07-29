function registerSettingsIpcHandlers({
  ipcMain,
  validateSender,
  dialog,
  getMainWindow,
  getSettings,
  saveSettings,
  getSettingsWithSecrets,
  onSettingsSaved,
  discoverAdvisorModels,
  testAdvisorModel,
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

  ipcMain.handle('advisor-provider:list-models', async (event, payload = {}) => {
    validateSender(event)
    const settings = await getSettingsWithSecrets()
    const provider = payload.provider || settings.advisorProvider
    const submittedKey = String(payload.apiKey || '')
    let apiKey = submittedKey && !submittedKey.includes('...') ? submittedKey : ''
    if (!apiKey && provider === 'openrouter') apiKey = settings.openRouterApiKey
    if (!apiKey && provider === 'custom') apiKey = settings.customProviderApiKey

    return discoverAdvisorModels({
      provider,
      baseUrl: payload.baseUrl,
      apiKey,
    })
  })

  ipcMain.handle('advisor-provider:test-model', async (event, payload = {}) => {
    validateSender(event)
    const settings = await getSettingsWithSecrets()
    const provider = payload.provider || settings.advisorProvider
    const submittedKey = String(payload.apiKey || '')
    let apiKey = submittedKey && !submittedKey.includes('...') ? submittedKey : ''
    if (!apiKey && provider === 'openrouter') apiKey = settings.openRouterApiKey
    if (!apiKey && provider === 'custom') apiKey = settings.customProviderApiKey

    return testAdvisorModel({
      provider,
      baseUrl: payload.baseUrl,
      apiKey,
      model: payload.model,
    })
  })
}

module.exports = {
  registerSettingsIpcHandlers,
}
