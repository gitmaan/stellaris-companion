const path = require('path')
const fs = require('fs')

function registerExportIpcHandlers({ ipcMain, validateSender, dialog, getMainWindow, app }) {
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
}

module.exports = {
  registerExportIpcHandlers,
}
