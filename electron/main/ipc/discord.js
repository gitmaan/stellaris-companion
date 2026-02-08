function registerDiscordIpcHandlers({ ipcMain, validateSender, discordOAuth, discordRelay }) {
  if (!ipcMain) throw new Error('registerDiscordIpcHandlers: ipcMain is required')
  if (typeof validateSender !== 'function') throw new Error('registerDiscordIpcHandlers: validateSender() is required')
  if (!discordOAuth) throw new Error('registerDiscordIpcHandlers: discordOAuth is required')
  if (!discordRelay) throw new Error('registerDiscordIpcHandlers: discordRelay is required')

  // IPC handlers for Discord OAuth (DISC-007)
  ipcMain.handle('discord:connect', async (event) => {
    validateSender(event)
    return discordOAuth.startDiscordOAuth()
  })

  ipcMain.handle('discord:disconnect', async (event) => {
    validateSender(event)
    discordRelay.disconnectFromDiscordRelay()
    await discordOAuth.clearDiscordTokens()
    return { success: true }
  })

  ipcMain.handle('discord:status', async (event) => {
    validateSender(event)
    return discordOAuth.getDiscordConnectionStatus()
  })

  ipcMain.handle('discord:get-tokens', async (event) => {
    validateSender(event)
    // Only return tokens to trusted renderer for WebSocket connection
    return discordOAuth.getDiscordTokens()
  })

  // IPC handlers for Discord relay (DISC-008)
  ipcMain.handle('discord:relay-connect', async (event) => {
    validateSender(event)
    return await discordRelay.connectFromStoredTokens()
  })

  ipcMain.handle('discord:relay-disconnect', async (event) => {
    validateSender(event)
    discordRelay.disconnectFromDiscordRelay()
    return { success: true }
  })

  ipcMain.handle('discord:relay-status', async (event) => {
    validateSender(event)
    return discordRelay.getDiscordRelayConnectionState()
  })
}

module.exports = {
  registerDiscordIpcHandlers,
}

