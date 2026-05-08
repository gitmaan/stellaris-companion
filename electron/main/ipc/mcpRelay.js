function registerMcpRelayIpcHandlers({
  ipcMain,
  validateSender,
  shell,
  mcpRelayService,
}) {
  if (!ipcMain) throw new Error('registerMcpRelayIpcHandlers: ipcMain is required')
  if (typeof validateSender !== 'function') throw new Error('registerMcpRelayIpcHandlers: validateSender is required')
  if (!mcpRelayService) throw new Error('registerMcpRelayIpcHandlers: mcpRelayService is required')

  ipcMain.handle('mcp-relay:status', async (event) => {
    validateSender(event)
    return mcpRelayService.getStatus()
  })

  ipcMain.handle('mcp-relay:health-check', async (event) => {
    validateSender(event)
    return mcpRelayService.runHealthCheck()
  })

  ipcMain.handle('mcp-relay:install-claude-desktop', async (event) => {
    validateSender(event)
    return mcpRelayService.installClaudeDesktopConfig()
  })

  ipcMain.handle('mcp-relay:open-claude-config-folder', async (event) => {
    validateSender(event)
    const status = mcpRelayService.getStatus()
    const configPath = status?.claudeDesktop?.configPath
    if (!configPath || !shell?.showItemInFolder) return { success: false }
    shell.showItemInFolder(configPath)
    return { success: true }
  })
}

module.exports = {
  registerMcpRelayIpcHandlers,
}
