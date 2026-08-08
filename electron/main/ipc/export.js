const path = require('path')
const fs = require('fs')

function registerExportIpcHandlers({
  ipcMain,
  validateSender,
  dialog,
  getMainWindow,
  app,
  shell,
  callBackendApiEnvelope,
}) {
  ipcMain.handle('export-chronicle', async (event, { html, defaultFilename }) => {
    validateSender(event)

    const documentsDir = app.getPath('documents')
    const defaultPath = path.join(documentsDir, defaultFilename || 'Chronicle.html')

    const result = await dialog.showSaveDialog(getMainWindow(), {
      defaultPath,
      filters: [{ name: 'HTML', extensions: ['html'] }],
    })

    if (result.canceled || !result.filePath) {
      return null
    }

    try {
      await fs.promises.writeFile(result.filePath, html, 'utf-8')
      return { success: true, filePath: result.filePath }
    } catch (err) {
      return { success: false, error: err instanceof Error ? err.message : 'Failed to write file' }
    }
  })

  ipcMain.handle('history:reveal-data', async (event) => {
    validateSender(event)
    const dbPath = path.join(app.getPath('userData'), 'stellaris_history.db')
    shell.showItemInFolder(dbPath)
    return { success: true, path: dbPath }
  })

  ipcMain.handle('history:backup', async (event) => {
    validateSender(event)
    const defaultPath = path.join(
      app.getPath('documents'),
      `Stellaris Companion History Backup ${new Date().toISOString().slice(0, 10)}.db`,
    )
    const result = await dialog.showSaveDialog(getMainWindow(), {
      defaultPath,
      filters: [{ name: 'SQLite database', extensions: ['db'] }],
    })
    if (result.canceled || !result.filePath) return null
    return await callBackendApiEnvelope('/api/history/backup', {
      method: 'POST',
      body: JSON.stringify({ destination: result.filePath }),
    })
  })
}

module.exports = {
  registerExportIpcHandlers,
}
