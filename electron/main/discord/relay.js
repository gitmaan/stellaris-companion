// Discord Relay WebSocket Client (DISC-008)
const WebSocket = require('ws')

function createDiscordRelay({
  relayUrl,
  getMainWindow,
  callBackendApiOrThrow,
  getDiscordTokens,
  ensureValidTokens,
}) {
  if (!relayUrl) throw new Error('createDiscordRelay: relayUrl is required')
  if (typeof getMainWindow !== 'function') throw new Error('createDiscordRelay: getMainWindow() is required')
  if (typeof callBackendApiOrThrow !== 'function') throw new Error('createDiscordRelay: callBackendApiOrThrow() is required')
  if (typeof getDiscordTokens !== 'function') throw new Error('createDiscordRelay: getDiscordTokens() is required')
  if (typeof ensureValidTokens !== 'function') throw new Error('createDiscordRelay: ensureValidTokens() is required')

  // DISC-008: Reconnection configuration per architecture spec
  const RECONNECT_CONFIG = {
    initialDelayMs: 1000,      // First retry after 1 second
    maxDelayMs: 30000,         // Cap at 30 seconds
    backoffMultiplier: 2,      // Double each time
    maxRetries: 10,            // Give up after 10 attempts
    jitterPercent: 20,         // Add ±20% randomness to prevent thundering herd
  }

  // WebSocket state
  let discordRelaySocket = null
  let discordRelayRetryCount = 0
  let discordRelayRetryDelay = RECONNECT_CONFIG.initialDelayMs
  let discordRelayReconnectTimer = null
  let discordRelayConnectionState = 'disconnected' // 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error'
  let discordRelayUserId = null
  let discordRelayLastConnectedAt = null // DISC-016: Track last successful connection time
  let discordRelayError = null // DISC-016: Track error message for error state

  function sendToRenderer(channel, payload) {
    const mainWindow = getMainWindow()
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send(channel, payload)
    }
  }

  /**
   * Get the current Discord relay connection state.
   * DISC-016: Includes lastConnectedAt for showing 'Last connected: X ago' during reconnecting
   * @returns {Object} Connection state info
   */
  function getDiscordRelayConnectionState() {
    return {
      state: discordRelayConnectionState,
      userId: discordRelayUserId,
      retryCount: discordRelayRetryCount,
      lastConnectedAt: discordRelayLastConnectedAt, // DISC-016: For reconnecting UI
      error: discordRelayError, // DISC-016: For error state UI
    }
  }

  /**
   * Update connection state and notify renderer.
   * DISC-016: Includes lastConnectedAt and error for full status indicator
   * @param {string} state - New connection state
   * @param {string} [errorMsg] - Optional error message for error state
   */
  function updateDiscordRelayConnectionState(state, errorMsg = null) {
    discordRelayConnectionState = state
    discordRelayError = errorMsg
    sendToRenderer('discord-relay-status', {
      state,
      userId: discordRelayUserId,
      retryCount: discordRelayRetryCount,
      lastConnectedAt: discordRelayLastConnectedAt, // DISC-016: For 'Last connected: X ago'
      error: discordRelayError, // DISC-016: For error state display
    })
  }

  /**
   * Get a relay token from the Cloudflare relay service.
   *
   * @param {string} discordAccessToken - Discord OAuth access token
   * @returns {Promise<string|null>} Relay token or null on failure
   */
  async function getRelayToken(discordAccessToken) {
    try {
      const response = await fetch(`${relayUrl}/relay/session`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${discordAccessToken}`,
          'Content-Type': 'application/json',
        },
      })

      if (!response.ok) {
        const errorText = await response.text()
        console.error('Failed to get relay token:', response.status, errorText)
        return null
      }

      const data = await response.json()
      return data.relay_token
    } catch (e) {
      console.error('Error getting relay token:', e.message)
      return null
    }
  }

  /**
   * Connect to the Discord relay WebSocket.
   * Authenticates with relay_token in Authorization header.
   *
   * DISC-008: WebSocket client connecting to Cloudflare DO
   *
   * @param {string} relayToken - The relay token from /relay/session
   * @param {string} userId - The Discord user ID
   * @returns {Promise<boolean>} True if connection initiated
   */
  async function connectToDiscordRelay(relayToken, userId) {
    // Close any existing connection
    if (discordRelaySocket) {
      try {
        discordRelaySocket.close(1000, 'Reconnecting')
      } catch (e) {
        // ignore
      }
      discordRelaySocket = null
    }

    // Clear any pending reconnect timer
    if (discordRelayReconnectTimer) {
      clearTimeout(discordRelayReconnectTimer)
      discordRelayReconnectTimer = null
    }

    discordRelayUserId = userId
    updateDiscordRelayConnectionState('connecting')

    try {
      // DISC-008: Connect with Authorization header containing relay_token
      discordRelaySocket = new WebSocket(`${relayUrl}/ws`, {
        headers: {
          Authorization: `Bearer ${relayToken}`,
        },
      })

      discordRelaySocket.on('open', () => {
        console.log('Discord relay WebSocket connected')
        discordRelayRetryCount = 0
        discordRelayRetryDelay = RECONNECT_CONFIG.initialDelayMs
        discordRelayLastConnectedAt = Date.now() // DISC-016: Track last successful connection
        updateDiscordRelayConnectionState('connected')

        // Send auth message with userId (DO expects this after connection)
        discordRelaySocket.send(JSON.stringify({
          type: 'auth',
          userId: userId,
        }))
      })

      discordRelaySocket.on('message', async (data) => {
        await handleDiscordRelayMessage(data)
      })

      discordRelaySocket.on('close', (code, reason) => {
        console.log(`Discord relay WebSocket closed: code=${code}, reason=${reason}`)
        handleDiscordRelayClose(code, reason?.toString() || '', relayToken, userId)
      })

      discordRelaySocket.on('error', (err) => {
        console.error('Discord relay WebSocket error:', err.message)
      })

      return true
    } catch (e) {
      console.error('Failed to connect to Discord relay:', e)
      updateDiscordRelayConnectionState('disconnected')
      return false
    }
  }

  /**
   * Handle /ask command from Discord relay.
   * Routes to local Python backend's /api/chat endpoint.
   *
   * DISC-008: Route incoming 'ask' messages to POST /api/chat
   *
   * @param {Object} message - The ask command message
   */
  async function handleDiscordAskCommand(message) {
    const { interactionToken, question, userId, guildId, channelId } = message

    if (!interactionToken || !question) {
      console.error('Discord relay: invalid ask command', message)
      return
    }

    console.log(`Discord relay: processing /ask from user ${userId}: "${question.substring(0, 50)}..."`)

    try {
      // Build session key per DISC-009 pattern: discord:{user_id}:{guild_id}:{channel_id}
      const sessionKey = `discord:${userId}:${guildId || 'dm'}:${channelId || 'dm'}`

      // Call the local Python backend /api/chat endpoint
      const response = await callBackendApiOrThrow('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: question,
          session_key: sessionKey,
        }),
      })

      // Send response back through WebSocket
      if (discordRelaySocket && discordRelaySocket.readyState === WebSocket.OPEN) {
        discordRelaySocket.send(JSON.stringify({
          type: 'response',
          interactionToken,
          text: response.text || response.response || 'No response from advisor',
        }))
        console.log('Discord relay: sent response back to relay')
      } else {
        console.error('Discord relay: WebSocket not connected, cannot send response')
      }
    } catch (e) {
      console.error('Discord relay: error calling backend:', e.message)

      // Send error response back
      if (discordRelaySocket && discordRelaySocket.readyState === WebSocket.OPEN) {
        discordRelaySocket.send(JSON.stringify({
          type: 'response',
          interactionToken,
          text: `⚠️ Error: ${e.message || 'Failed to get response from advisor'}`,
        }))
      }
    }
  }

  /**
   * Handle incoming message from Discord relay.
   *
   * DISC-008: Handle incoming /ask messages and route to backend
   *
   * @param {Buffer|string} data - Raw WebSocket message
   */
  async function handleDiscordRelayMessage(data) {
    try {
      const message = JSON.parse(data.toString())
      const { type } = message

      switch (type) {
        case 'auth_ok':
          console.log('Discord relay authenticated successfully')
          break

        case 'auth_error':
          console.error('Discord relay auth error:', message.reason)
          updateDiscordRelayConnectionState('disconnected')
          break

        case 'replaced':
          // Another device connected - don't retry
          console.log('Discord relay: connection replaced by another device')
          updateDiscordRelayConnectionState('disconnected')
          discordRelaySocket = null
          break

        case 'ask':
          // DISC-008: Handle /ask command from Discord - route to /api/chat
          await handleDiscordAskCommand(message)
          break

        default:
          console.log('Discord relay: unknown message type:', type)
      }
    } catch (e) {
      console.error('Failed to parse Discord relay message:', e)
    }
  }

  /**
   * Reconnect to Discord relay, refreshing token if needed.
   *
   * DISC-011: Uses ensureValidTokens to auto-refresh Discord tokens before reconnecting
   *
   * @param {string} relayToken - Current relay token (may be expired)
   * @param {string} userId - Discord user ID
   */
  async function reconnectToDiscordRelay(relayToken, userId) {
    try {
      // DISC-011: Ensure we have valid Discord tokens, auto-refresh if needed
      let tokens
      try {
        tokens = await ensureValidTokens()
      } catch (tokenError) {
        if (tokenError.message === 'NOT_AUTHENTICATED' || tokenError.message === 'TOKEN_EXPIRED') {
          console.log('Discord relay: authentication expired, need re-auth')
          updateDiscordRelayConnectionState('disconnected')
          // Notify renderer that re-auth is needed
          sendToRenderer('discord-auth-required', {
            reason: tokenError.message === 'TOKEN_EXPIRED' ? 'Token expired' : 'Not authenticated',
          })
          return
        }
        throw tokenError
      }

      // Get fresh relay token from the relay service using the (possibly refreshed) Discord token
      const freshRelayToken = await getRelayToken(tokens.accessToken)
      if (!freshRelayToken) {
        console.log('Discord relay: failed to get fresh relay token')
        // Continue with existing token as fallback
        await connectToDiscordRelay(relayToken, userId)
      } else {
        await connectToDiscordRelay(freshRelayToken, tokens.userId)
      }
    } catch (e) {
      console.error('Discord relay: reconnect failed:', e.message)
      updateDiscordRelayConnectionState('disconnected')
    }
  }

  /**
   * Handle WebSocket close event with reconnection logic.
   *
   * DISC-008: Reconnection with exponential backoff
   *
   * @param {number} code - WebSocket close code
   * @param {string} reason - Close reason
   * @param {string} relayToken - Token for reconnection
   * @param {string} userId - User ID for reconnection
   */
  function handleDiscordRelayClose(code, reason, relayToken, userId) {
    discordRelaySocket = null

    // DISC-008: Handle special close codes
    if (code === 4001) {
      // Auth revoked - don't retry, prompt re-auth
      console.log('Discord relay: auth revoked, not retrying')
      updateDiscordRelayConnectionState('disconnected')
      return
    }

    if (code === 4002) {
      // Replaced by another device - don't retry
      console.log('Discord relay: replaced by another device, not retrying')
      updateDiscordRelayConnectionState('disconnected')
      return
    }

    // Code 1006 or 1001 often indicates deploy/server restart - reconnect quickly
    if (code === 1006 || code === 1001) {
      console.log('Discord relay: connection lost (possibly deploy), reconnecting quickly...')
      discordRelayReconnectTimer = setTimeout(() => {
        reconnectToDiscordRelay(relayToken, userId)
      }, 1000)
      updateDiscordRelayConnectionState('reconnecting')
      return
    }

    // Normal reconnection with exponential backoff
    if (discordRelayRetryCount >= RECONNECT_CONFIG.maxRetries) {
      console.log('Discord relay: max retries exceeded, giving up')
      // DISC-016: Use 'error' state when max retries exceeded (shows red indicator)
      updateDiscordRelayConnectionState('error', 'Unable to connect after 10 attempts')
      return
    }

    updateDiscordRelayConnectionState('reconnecting')

    // DISC-008: Exponential backoff with jitter
    const jitter = discordRelayRetryDelay * RECONNECT_CONFIG.jitterPercent / 100
    const delay = discordRelayRetryDelay + (Math.random() * 2 - 1) * jitter

    console.log(`Discord relay: reconnecting in ${Math.round(delay)}ms (attempt ${discordRelayRetryCount + 1}/${RECONNECT_CONFIG.maxRetries})`)

    discordRelayReconnectTimer = setTimeout(() => {
      discordRelayRetryCount++
      discordRelayRetryDelay = Math.min(
        discordRelayRetryDelay * RECONNECT_CONFIG.backoffMultiplier,
        RECONNECT_CONFIG.maxDelayMs
      )
      reconnectToDiscordRelay(relayToken, userId)
    }, delay)
  }

  /**
   * Disconnect from Discord relay.
   */
  function disconnectFromDiscordRelay() {
    // Clear any pending reconnect
    if (discordRelayReconnectTimer) {
      clearTimeout(discordRelayReconnectTimer)
      discordRelayReconnectTimer = null
    }

    // Close socket
    if (discordRelaySocket) {
      try {
        // Send disconnect message first
        if (discordRelaySocket.readyState === WebSocket.OPEN) {
          discordRelaySocket.send(JSON.stringify({ type: 'disconnect' }))
        }
        discordRelaySocket.close(1000, 'User disconnected')
      } catch (e) {
        // ignore
      }
      discordRelaySocket = null
    }

    discordRelayUserId = null
    discordRelayRetryCount = 0
    discordRelayRetryDelay = RECONNECT_CONFIG.initialDelayMs
    updateDiscordRelayConnectionState('disconnected')
  }

  /**
   * Start Discord relay connection if user is connected to Discord.
   * Called after OAuth completes or on app startup.
   */
  async function startDiscordRelayIfConnected() {
    const tokens = await getDiscordTokens()
    if (!tokens || !tokens.accessToken) {
      console.log('Discord relay: not connected to Discord, skipping relay connection')
      return
    }

    console.log('Discord relay: user is connected to Discord, establishing relay connection...')

    // Get relay token
    const relayToken = await getRelayToken(tokens.accessToken)
    if (!relayToken) {
      console.error('Discord relay: failed to get relay token')
      return
    }

    // Connect to relay
    await connectToDiscordRelay(relayToken, tokens.userId)
  }

  /**
   * Used by IPC handler: connect using stored tokens, return status for UI.
   */
  async function connectFromStoredTokens() {
    const tokens = await getDiscordTokens()
    if (!tokens || !tokens.accessToken) {
      return { success: false, error: 'Not connected to Discord' }
    }

    const relayToken = await getRelayToken(tokens.accessToken)
    if (!relayToken) {
      return { success: false, error: 'Failed to get relay token' }
    }

    const connected = await connectToDiscordRelay(relayToken, tokens.userId)
    return { success: connected }
  }

  return {
    startDiscordRelayIfConnected,
    connectFromStoredTokens,
    disconnectFromDiscordRelay,
    getDiscordRelayConnectionState,
  }
}

module.exports = {
  createDiscordRelay,
}

