function registerBackendIpcHandlers({ ipcMain, validateSender, callBackendApiEnvelope, getResolvedLanguage }) {
  // IPC Handlers - Backend Proxy (requires ELEC-005 for full implementation)
  // Basic handlers for backend proxy

  const withLanguage = (body = {}) => ({
    ...body,
    language: typeof getResolvedLanguage === 'function' ? getResolvedLanguage() : 'en',
  })

  const safeHandle = (channel, handler) => {
    ipcMain.handle(channel, async (event, ...args) => {
      try {
        validateSender(event)
      } catch (error) {
        return {
          ok: false,
          error: error instanceof Error ? error.message : 'IPC error',
          code: 'IPC_SENDER_INVALID',
        }
      }
      return await handler(...args)
    })
  }

  safeHandle('backend:health', async () => {
    return await callBackendApiEnvelope('/api/health')
  })

  safeHandle('backend:diagnostics', async () => {
    return await callBackendApiEnvelope('/api/diagnostics')
  })

  safeHandle('backend:chat', async ({ message, session_key, model, model_routing_mode }) => {
    return await callBackendApiEnvelope('/api/chat', {
      method: 'POST',
      body: JSON.stringify(withLanguage({
        message,
        session_key,
        model: model || null,
        model_routing_mode: model_routing_mode || null,
      })),
    })
  })

  safeHandle('backend:status', async () => {
    return await callBackendApiEnvelope('/api/status')
  })

  safeHandle('backend:sessions', async () => {
    return await callBackendApiEnvelope('/api/sessions')
  })

  safeHandle('backend:playthroughs', async ({ include_trashed } = {}) => {
    const language = typeof getResolvedLanguage === 'function' ? getResolvedLanguage() : 'en'
    const query = new URLSearchParams({
      language,
      include_trashed: include_trashed === false ? 'false' : 'true',
    })
    return await callBackendApiEnvelope(`/api/playthroughs?${query.toString()}`)
  })

  safeHandle('backend:cached-chronicle', async ({ save_id }) => {
    const language = typeof getResolvedLanguage === 'function' ? getResolvedLanguage() : 'en'
    const query = new URLSearchParams({ language })
    return await callBackendApiEnvelope(`/api/playthroughs/${encodeURIComponent(save_id)}/chronicle?${query.toString()}`)
  })

  safeHandle('backend:set-playthrough-label', async ({ save_id, display_label }) => {
    return await callBackendApiEnvelope(`/api/playthroughs/${encodeURIComponent(save_id)}/label`, {
      method: 'POST',
      body: JSON.stringify({ display_label }),
    })
  })

  safeHandle('backend:trash-playthrough', async ({ save_id }) => {
    return await callBackendApiEnvelope(`/api/playthroughs/${encodeURIComponent(save_id)}/trash`, {
      method: 'POST',
    })
  })

  safeHandle('backend:restore-playthrough', async ({ save_id }) => {
    return await callBackendApiEnvelope(`/api/playthroughs/${encodeURIComponent(save_id)}/restore`, {
      method: 'POST',
    })
  })

  safeHandle('backend:reset-chronicle', async ({ save_id }) => {
    return await callBackendApiEnvelope(`/api/playthroughs/${encodeURIComponent(save_id)}/reset-chronicle`, {
      method: 'POST',
      body: JSON.stringify(withLanguage({ confirm: true })),
    })
  })

  safeHandle('backend:undo-chronicle-reset', async ({ save_id }) => {
    return await callBackendApiEnvelope(`/api/playthroughs/${encodeURIComponent(save_id)}/undo-reset`, {
      method: 'POST',
      body: JSON.stringify(withLanguage()),
    })
  })

  safeHandle('backend:delete-playthrough', async ({ save_id }) => {
    return await callBackendApiEnvelope(`/api/playthroughs/${encodeURIComponent(save_id)}?confirm=true`, {
      method: 'DELETE',
    })
  })

  safeHandle('backend:history-storage', async () => {
    return await callBackendApiEnvelope('/api/history/storage')
  })

  safeHandle('backend:session-events', async ({ session_id, limit }) => {
    let url = `/api/sessions/${session_id}/events`
    if (limit) {
      url += `?limit=${limit}`
    }
    return await callBackendApiEnvelope(url)
  })

  safeHandle('backend:recap', async ({ session_id, style, model_routing_mode }) => {
    return await callBackendApiEnvelope('/api/recap', {
      method: 'POST',
      body: JSON.stringify(withLanguage({
        session_id,
        style: style || 'summary',
        model_routing_mode: model_routing_mode || null,
      })),
    })
  })

  safeHandle('backend:chronicle', async ({ session_id, force_refresh, chapter_only, refresh_mode, model_routing_mode }) => {
    return await callBackendApiEnvelope('/api/chronicle', {
      method: 'POST',
      body: JSON.stringify(withLanguage({
        session_id,
        force_refresh: force_refresh || false,
        chapter_only: chapter_only || false,
        refresh_mode: refresh_mode || 'balanced',
        model_routing_mode: model_routing_mode || null,
      })),
    })
  })

  safeHandle('backend:regenerate-chapter', async ({ session_id, chapter_number, confirm, regeneration_instructions, model_routing_mode }) => {
    return await callBackendApiEnvelope('/api/chronicle/regenerate-chapter', {
      method: 'POST',
      body: JSON.stringify(withLanguage({
        session_id,
        chapter_number,
        confirm: confirm || false,
        regeneration_instructions: regeneration_instructions || null,
        model_routing_mode: model_routing_mode || null,
      })),
    })
  })

  safeHandle('backend:end-session', async () => {
    return await callBackendApiEnvelope('/api/end-session', {
      method: 'POST',
    })
  })

  safeHandle('backend:get-chronicle-custom', async () => {
    return await callBackendApiEnvelope('/api/chronicle-custom-instructions')
  })

  safeHandle('backend:set-chronicle-custom', async ({ custom_instructions }) => {
    return await callBackendApiEnvelope('/api/chronicle-custom-instructions', {
      method: 'POST',
      body: JSON.stringify({ custom_instructions }),
    })
  })

  safeHandle('backend:get-session-advisor-custom', async () => {
    return await callBackendApiEnvelope('/api/session-advisor-custom')
  })

  safeHandle('backend:set-session-advisor-custom', async ({ custom_instructions }) => {
    return await callBackendApiEnvelope('/api/session-advisor-custom', {
      method: 'POST',
      body: JSON.stringify({ custom_instructions }),
    })
  })
}

module.exports = {
  registerBackendIpcHandlers,
}
