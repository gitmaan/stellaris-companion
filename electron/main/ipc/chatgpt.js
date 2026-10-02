const { ChatGPTError } = require('../chatgpt')

function registerChatGPTIpcHandlers({ ipcMain, validateSender, service, activate, changed }) {
  const operations = {
    status: () => service.status(),
    connect: options => service.signIn({ profileId: options?.profileId, newAccount: options?.newAccount === true }),
    cancel: () => { service.cancel(); return service.status() },
    reopen: () => service.reopen(),
    'select-account': id => service.selectAccount(String(id)),
    'select-model': model => service.selectModel(String(model)),
    disconnect: () => service.disconnect(),
    check: () => service.check(),
    models: async () => { await service.listModels(); return service.status() },
    'acknowledge-welcome': () => { service.acknowledgeWelcome(); return service.status() },
  }
  for (const [name, operation] of Object.entries(operations)) {
    ipcMain.handle(`chatgpt:${name}`, async (event, payload) => {
      validateSender(event)
      try {
        const status = await operation(payload)
        if (['connect', 'select-account', 'select-model', 'check'].includes(name) && status.ready) await activate(status, name)
        if (name === 'disconnect') await changed()
        return { ok: true, status }
      } catch (error) {
        // Electron's default exception serialization can expose request details.
        return { ok: false, status: service.status(), code: error instanceof ChatGPTError ? error.code : 'CHATGPT_UNAVAILABLE' }
      }
    })
  }
}
module.exports = { registerChatGPTIpcHandlers }
