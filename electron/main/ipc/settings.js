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
  openRouterOAuth,
  translate,
}) {
  ipcMain.handle('load-settings', async (event) => {
    validateSender(event)
    return getSettings()
  })

  ipcMain.handle('save-settings', async (event, settings) => {
    validateSender(event)
    const pendingCredential = settings?.openRouterCredentialId
    const values = { ...settings }
    delete values.openRouterCredentialId
    if (pendingCredential) {
      values.openRouterApiKey = openRouterOAuth.getKey(pendingCredential)
    }
    await saveSettings(values)
    if (pendingCredential) openRouterOAuth.discard(pendingCredential)

    const fullSettings = await getSettingsWithSecrets()
    await onSettingsSaved(fullSettings, values)

    const saved = getSettings()
    return { success: true, language: saved.language, resolvedLanguage: saved.resolvedLanguage }
  })

  ipcMain.handle('select-folder', async (event) => {
    validateSender(event)
    const result = await dialog.showOpenDialog(getMainWindow(), {
      properties: ['openDirectory'],
      title: translate('dialogs.selectSaveFolder'),
    })

    if (result.canceled || !result.filePaths.length) {
      return null
    }

    return result.filePaths[0]
  })

  const resolveKey = (payload, settings, provider) => {
    if (provider === 'openrouter' && payload.credentialId) {
      return openRouterOAuth.getKey(payload.credentialId)
    }
    const submitted = payload.apiKey
    if (typeof submitted === 'string' && !submitted.includes('...')) return submitted.trim()
    if (provider === 'gemini') return settings.googleApiKey
    if (provider === 'openrouter') return settings.openRouterApiKey
    if (provider === 'custom') return settings.customProviderApiKey
    return ''
  }

  for (const [channel, operation] of [
    ['advisor-provider:list-models', discoverAdvisorModels],
    ['advisor-provider:test-model', testAdvisorModel],
  ]) {
    ipcMain.handle(channel, async (event, payload = {}) => {
      validateSender(event)
      const settings = await getSettingsWithSecrets()
      const provider = payload.provider || settings.advisorProvider
      try {
        return await operation({ provider, baseUrl: payload.baseUrl, apiKey: resolveKey(payload, settings, provider), model: payload.model })
      } catch {
        return { ok: false, errorCode: 'PROVIDER_AUTH_FAILED', error: 'Connect your provider again.' }
      }
    })
  }

  ipcMain.handle('advisor-provider:connect-openrouter', async event => {
    validateSender(event)
    return openRouterOAuth.connect()
  })
  ipcMain.handle('advisor-provider:cancel-openrouter', event => {
    validateSender(event)
    openRouterOAuth.cancel()
    return { ok: true }
  })
}

module.exports = { registerSettingsIpcHandlers }
