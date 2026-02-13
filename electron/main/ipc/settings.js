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
}

module.exports = {
  registerSettingsIpcHandlers,
}
