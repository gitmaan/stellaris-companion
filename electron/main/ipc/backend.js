function registerBackendIpcHandlers({ ipcMain, validateSender, callBackendApiEnvelope }) {
  // IPC Handlers - Backend Proxy (requires ELEC-005 for full implementation)
  // Basic handlers for backend proxy

  ipcMain.handle('backend:health', async (event) => {
    try { validateSender(event) } catch (e) { return { ok: false, error: e instanceof Error ? e.message : 'IPC error', code: 'IPC_SENDER_INVALID' } }
    return await callBackendApiEnvelope('/api/health')
  })

  ipcMain.handle('backend:diagnostics', async (event) => {
    try { validateSender(event) } catch (e) { return { ok: false, error: e instanceof Error ? e.message : 'IPC error', code: 'IPC_SENDER_INVALID' } }
    return await callBackendApiEnvelope('/api/diagnostics')
  })

  ipcMain.handle('backend:chat', async (event, { message, session_key }) => {
    try { validateSender(event) } catch (e) { return { ok: false, error: e instanceof Error ? e.message : 'IPC error', code: 'IPC_SENDER_INVALID' } }
    return await callBackendApiEnvelope('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message, session_key }),
    })
  })

  ipcMain.handle('backend:status', async (event) => {
    try { validateSender(event) } catch (e) { return { ok: false, error: e instanceof Error ? e.message : 'IPC error', code: 'IPC_SENDER_INVALID' } }
    return await callBackendApiEnvelope('/api/status')
  })

  ipcMain.handle('backend:sessions', async (event) => {
    try { validateSender(event) } catch (e) { return { ok: false, error: e instanceof Error ? e.message : 'IPC error', code: 'IPC_SENDER_INVALID' } }
    return await callBackendApiEnvelope('/api/sessions')
  })

  ipcMain.handle('backend:session-events', async (event, { session_id, limit }) => {
    try { validateSender(event) } catch (e) { return { ok: false, error: e instanceof Error ? e.message : 'IPC error', code: 'IPC_SENDER_INVALID' } }
    let url = `/api/sessions/${session_id}/events`
    if (limit) {
      url += `?limit=${limit}`
    }
    return await callBackendApiEnvelope(url)
  })

  ipcMain.handle('backend:recap', async (event, { session_id, style }) => {
    try { validateSender(event) } catch (e) { return { ok: false, error: e instanceof Error ? e.message : 'IPC error', code: 'IPC_SENDER_INVALID' } }
    return await callBackendApiEnvelope('/api/recap', {
      method: 'POST',
      body: JSON.stringify({ session_id, style: style || 'summary' }),
    })
  })

  ipcMain.handle('backend:chronicle', async (event, { session_id, force_refresh, chapter_only }) => {
    try { validateSender(event) } catch (e) { return { ok: false, error: e instanceof Error ? e.message : 'IPC error', code: 'IPC_SENDER_INVALID' } }
    return await callBackendApiEnvelope('/api/chronicle', {
      method: 'POST',
      body: JSON.stringify({
        session_id,
        force_refresh: force_refresh || false,
        chapter_only: chapter_only || false,
      }),
    })
  })

  ipcMain.handle('backend:regenerate-chapter', async (event, { session_id, chapter_number, confirm, regeneration_instructions }) => {
    try { validateSender(event) } catch (e) { return { ok: false, error: e instanceof Error ? e.message : 'IPC error', code: 'IPC_SENDER_INVALID' } }
    return await callBackendApiEnvelope('/api/chronicle/regenerate-chapter', {
      method: 'POST',
      body: JSON.stringify({ session_id, chapter_number, confirm: confirm || false, regeneration_instructions: regeneration_instructions || null }),
    })
  })

  ipcMain.handle('backend:end-session', async (event) => {
    try { validateSender(event) } catch (e) { return { ok: false, error: e instanceof Error ? e.message : 'IPC error', code: 'IPC_SENDER_INVALID' } }
    return await callBackendApiEnvelope('/api/end-session', {
      method: 'POST',
    })
  })

  ipcMain.handle('backend:get-chronicle-custom', async (event) => {
    try { validateSender(event) } catch (e) { return { ok: false, error: e instanceof Error ? e.message : 'IPC error', code: 'IPC_SENDER_INVALID' } }
    return await callBackendApiEnvelope('/api/chronicle-custom-instructions')
  })

  ipcMain.handle('backend:set-chronicle-custom', async (event, { custom_instructions }) => {
    try { validateSender(event) } catch (e) { return { ok: false, error: e instanceof Error ? e.message : 'IPC error', code: 'IPC_SENDER_INVALID' } }
    return await callBackendApiEnvelope('/api/chronicle-custom-instructions', {
      method: 'POST',
      body: JSON.stringify({ custom_instructions }),
    })
  })

  ipcMain.handle('backend:get-session-advisor-custom', async (event) => {
    try { validateSender(event) } catch (e) { return { ok: false, error: e instanceof Error ? e.message : 'IPC error', code: 'IPC_SENDER_INVALID' } }
    return await callBackendApiEnvelope('/api/session-advisor-custom')
  })

  ipcMain.handle('backend:set-session-advisor-custom', async (event, { custom_instructions }) => {
    try { validateSender(event) } catch (e) { return { ok: false, error: e instanceof Error ? e.message : 'IPC error', code: 'IPC_SENDER_INVALID' } }
    return await callBackendApiEnvelope('/api/session-advisor-custom', {
      method: 'POST',
      body: JSON.stringify({ custom_instructions }),
    })
  })
}

module.exports = {
  registerBackendIpcHandlers,
}
