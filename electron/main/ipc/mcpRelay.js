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

  ipcMain.handle('mcp-relay:connect-client', async (event, payload) => {
    validateSender(event)
    const client = payload?.client
    if (client === 'claude') return mcpRelayService.installClaudeDesktopConfig()
    if (client === 'codex') return mcpRelayService.installCodexConfig()
    if (client === 'cursor') return mcpRelayService.installCursorConfig()
    return { success: false, error: 'Unsupported MCP client.' }
  })

  ipcMain.handle('mcp-relay:disconnect-client', async (event, payload) => {
    validateSender(event)
    const client = payload?.client
    if (client === 'claude') return mcpRelayService.disconnectClaudeDesktopConfig()
    if (client === 'codex') return mcpRelayService.disconnectCodexConfig()
    if (client === 'cursor') return mcpRelayService.disconnectCursorConfig()
    return { success: false, error: 'Unsupported MCP client.' }
  })

  ipcMain.handle('mcp-relay:open-claude-extension', async (event) => {
    validateSender(event)
    const extensionPath = mcpRelayService.getBundledMcpbPath()
    if (!extensionPath || !shell?.openPath) return { success: false }
    const error = await shell.openPath(extensionPath)
    return error ? { success: false, error } : { success: true }
  })

  ipcMain.handle('mcp-relay:reveal-path', async (event, payload) => {
    validateSender(event)
    const status = mcpRelayService.getStatus()
    const allowed = new Set([
      status?.claudeDesktop?.configPath,
      status?.cursor?.configPath,
      status?.logPath,
    ].filter(Boolean))
    const requested = payload?.path
    if (!allowed.has(requested) || !shell?.showItemInFolder) return { success: false }
    shell.showItemInFolder(requested)
    return { success: true }
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
