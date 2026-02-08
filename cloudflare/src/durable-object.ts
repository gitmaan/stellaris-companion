/**
 * UserSession Durable Object
 *
 * Manages WebSocket connection between Cloudflare and a user's Electron app.
 * Uses hibernatable WebSocket API for cost efficiency.
 *
 * Responsibilities:
 * - Accept WebSocket connections from authenticated Electron clients
 * - Forward Discord commands to Electron
 * - Receive responses from Electron and forward to Discord
 * - Handle connection lifecycle (auth, replace, disconnect)
 */

// Import Discord utilities for webhook follow-up
import { editInteractionResponse, createFollowUpMessage, splitResponse } from './discord'

export interface Env {
  DISCORD_APP_ID: string
  DISCORD_PUBLIC_KEY: string
  DISCORD_BOT_TOKEN?: string
  RELAY_SIGNING_SECRET: string
}

/**
 * Session metadata stored in DO storage
 */
interface SessionData {
  userId: string
  lastSeen: number
}

/**
 * Pending request awaiting response from Electron
 * Stores interaction token and app ID for Discord webhook callback
 */
interface PendingRequest {
  interactionToken: string
  appId: string
  timestamp: number
}

/**
 * Session TTL - 7 days in milliseconds
 * Sessions without activity for this duration will be cleaned up
 */
const SESSION_TTL_MS = 7 * 24 * 60 * 60 * 1000

/**
 * Response timeout for Electron (30 seconds)
 * If Electron doesn't respond within this time, send timeout error to Discord
 */
const RESPONSE_TIMEOUT_MS = 30000

/**
 * UserSession Durable Object
 *
 * One instance per authenticated Discord user.
 * Maintains WebSocket connection to user's Electron app.
 */
export class UserSession {
  private ctx: DurableObjectState
  private env: Env
  private userId: string | null = null

  // DISC-006: Track pending requests awaiting responses from Electron
  // Key: interactionToken, Value: request metadata
  private pendingRequests: Map<string, PendingRequest> = new Map()

  constructor(ctx: DurableObjectState, env: Env) {
    this.ctx = ctx
    this.env = env
  }

  /**
   * Get the active Electron WebSocket connection.
   * Uses ctx.getWebSockets() to survive hibernation - the instance variable
   * is lost when the DO hibernates, but the WebSocket stays connected.
   */
  private getElectronSocket(): WebSocket | null {
    const sockets = this.ctx.getWebSockets()
    return sockets.length > 0 ? sockets[0] : null
  }

  /**
   * Handle HTTP requests to this Durable Object
   * Primary use: WebSocket upgrade for Electron connections
   */
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url)

    // Handle WebSocket upgrade
    if (request.headers.get('Upgrade') === 'websocket') {
      return this.handleWebSocketUpgrade(request)
    }

    // Handle Discord command forwarding (called by Worker)
    if (url.pathname === '/forward' && request.method === 'POST') {
      return this.handleForwardCommand(request)
    }

    return new Response('Not Found', { status: 404 })
  }

  /**
   * Handle WebSocket upgrade request from Electron
   */
  private async handleWebSocketUpgrade(request: Request): Promise<Response> {
    console.log('[DO] handleWebSocketUpgrade called')

    // Create WebSocket pair
    const pair = new WebSocketPair()
    const [client, server] = [pair[0], pair[1]]

    // Use hibernation API for cost efficiency
    // This allows the DO to sleep when no messages are being processed
    this.ctx.acceptWebSocket(server)

    const socketsAfter = this.ctx.getWebSockets()
    console.log(`[DO] After acceptWebSocket: ${socketsAfter.length} socket(s)`)

    return new Response(null, {
      status: 101,
      webSocket: client,
    })
  }

  /**
   * Handle incoming WebSocket messages (hibernation API)
   * Called when DO wakes from hibernation to process a message
   */
  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    if (typeof message !== 'string') {
      return
    }

    try {
      const msg = JSON.parse(message)
      await this.handleMessage(ws, msg)
    } catch (e) {
      console.error('Failed to parse WebSocket message:', e)
    }
  }

  /**
   * Handle WebSocket close (hibernation API)
   */
  async webSocketClose(
    ws: WebSocket,
    code: number,
    reason: string,
    wasClean: boolean
  ): Promise<void> {
    // WebSocket closed - Cloudflare manages the socket lifecycle
    console.log(`WebSocket closed: code=${code}, reason=${reason}`)
  }

  /**
   * Handle WebSocket error (hibernation API)
   */
  async webSocketError(ws: WebSocket, error: unknown): Promise<void> {
    console.error('WebSocket error:', error)
  }

  /**
   * Process a parsed WebSocket message
   */
  private async handleMessage(
    ws: WebSocket,
    msg: Record<string, unknown>
  ): Promise<void> {
    const type = msg.type as string

    switch (type) {
      case 'auth':
        await this.handleAuth(ws, msg)
        break

      case 'response':
        await this.handleResponse(msg)
        break

      case 'disconnect':
        await this.handleDisconnect(ws)
        break

      default:
        console.log('Unknown message type:', type)
    }
  }

  /**
   * Handle authentication message from Electron
   */
  private async handleAuth(
    ws: WebSocket,
    msg: Record<string, unknown>
  ): Promise<void> {
    const userId = msg.userId as string

    if (!userId) {
      ws.send(JSON.stringify({ type: 'auth_error', reason: 'Missing userId' }))
      ws.close(4001, 'Auth failed')
      return
    }

    // If another connection exists, close it (last connection wins)
    const existingSockets = this.ctx.getWebSockets()
    for (const socket of existingSockets) {
      if (socket !== ws) {
        socket.send(JSON.stringify({ type: 'replaced' }))
        socket.close(4002, 'Replaced by new connection')
      }
    }

    this.userId = userId

    // Persist session data and set TTL alarm
    await this.updateLastSeen()

    ws.send(JSON.stringify({ type: 'auth_ok', userId }))
  }

  /**
   * Handle response from Electron (answer to Discord command)
   *
   * DISC-006: Full response handling - sends follow-up to Discord via webhook
   */
  private async handleResponse(msg: Record<string, unknown>): Promise<void> {
    const interactionToken = msg.interactionToken as string
    const text = msg.text as string

    if (!interactionToken || !text) {
      console.error('Invalid response message:', msg)
      return
    }

    // Update last seen and reset TTL alarm
    await this.updateLastSeen()

    // Get the pending request to retrieve appId
    const pending = this.pendingRequests.get(interactionToken)
    if (!pending) {
      console.error('No pending request found for interaction token:', interactionToken)
      // Try using env.DISCORD_APP_ID as fallback
      if (this.env.DISCORD_APP_ID) {
        await this.sendDiscordResponse(this.env.DISCORD_APP_ID, interactionToken, text)
      }
      return
    }

    // Remove from pending requests
    this.pendingRequests.delete(interactionToken)

    // DISC-006: Send follow-up to Discord via webhook
    await this.sendDiscordResponse(pending.appId, interactionToken, text)
  }

  /**
   * Send response to Discord via webhook
   *
   * Handles long responses by splitting them into multiple messages
   */
  private async sendDiscordResponse(
    appId: string,
    interactionToken: string,
    text: string
  ): Promise<void> {
    try {
      // Split response if it exceeds Discord's 2000 character limit
      const chunks = splitResponse(text)

      // Send first chunk as edit to original response
      const firstChunk = chunks[0]
      const response = await editInteractionResponse(appId, interactionToken, firstChunk, true)

      if (!response.ok) {
        console.error('Failed to send Discord response:', await response.text())
        return
      }

      // Send additional chunks as new follow-up messages
      for (let i = 1; i < chunks.length; i++) {
        const chunkResponse = await createFollowUpMessage(
          appId,
          interactionToken,
          chunks[i],
          true // ephemeral
        )

        if (!chunkResponse.ok) {
          console.error(`Failed to send chunk ${i + 1}/${chunks.length}:`, await chunkResponse.text())
          // Continue trying to send remaining chunks
        } else {
          console.log(`Sent chunk ${i + 1}/${chunks.length}`)
        }
      }

      console.log(`Discord response sent successfully (${chunks.length} chunk${chunks.length > 1 ? 's' : ''})`)
    } catch (error) {
      console.error('Error sending Discord response:', error)
    }
  }

  /**
   * Handle explicit disconnect from Electron
   */
  private async handleDisconnect(ws: WebSocket): Promise<void> {
    await this.ctx.storage.delete('session')
    this.userId = null
    ws.close(1000, 'Disconnect requested')
  }

  /**
   * Handle Discord command forwarding (called by Worker)
   *
   * DISC-006: Full command forwarding with pending request tracking
   */
  private async handleForwardCommand(request: Request): Promise<Response> {
    // DISC-006: Handle APP_OFFLINE - Electron not connected
    // Use getElectronSocket() to survive hibernation
    const allSockets = this.ctx.getWebSockets()
    console.log(`[DO] handleForwardCommand: found ${allSockets.length} WebSocket(s)`)

    const electronSocket = this.getElectronSocket()
    if (!electronSocket) {
      console.log('[DO] No electron socket found - returning APP_OFFLINE')
      return new Response(
        JSON.stringify({ error: 'APP_OFFLINE' }),
        { status: 503, headers: { 'Content-Type': 'application/json' } }
      )
    }

    console.log('[DO] Electron socket found, forwarding command')

    try {
      const command = await request.json() as Record<string, unknown>
      const interactionToken = command.interactionToken as string
      const appId = command.appId as string

      if (!interactionToken) {
        return new Response(
          JSON.stringify({ error: 'Missing interactionToken' }),
          { status: 400, headers: { 'Content-Type': 'application/json' } }
        )
      }

      // DISC-006: Store pending request for response handling
      this.pendingRequests.set(interactionToken, {
        interactionToken,
        appId: appId || this.env.DISCORD_APP_ID,
        timestamp: Date.now(),
      })

      // Set up timeout for this request
      // Note: We use setTimeout here but the DO may hibernate.
      // If the DO hibernates, we lose this timer. For production,
      // consider using DO storage + alarms for timeout handling.
      setTimeout(() => {
        this.handleRequestTimeout(interactionToken)
      }, RESPONSE_TIMEOUT_MS)

      // Forward command to Electron via WebSocket
      electronSocket.send(JSON.stringify({
        type: 'ask',
        interactionToken,
        question: command.question,
        userId: command.userId,
        guildId: command.guildId,
        channelId: command.channelId,
      }))

      return new Response(JSON.stringify({ success: true }), {
        headers: { 'Content-Type': 'application/json' },
      })
    } catch (e) {
      return new Response(
        JSON.stringify({ error: 'Failed to forward command' }),
        { status: 500, headers: { 'Content-Type': 'application/json' } }
      )
    }
  }

  /**
   * Handle request timeout - send error to Discord if Electron didn't respond
   */
  private async handleRequestTimeout(interactionToken: string): Promise<void> {
    const pending = this.pendingRequests.get(interactionToken)
    if (!pending) {
      // Already handled
      return
    }

    // Check if request actually timed out (in case of DO restart)
    const elapsed = Date.now() - pending.timestamp
    if (elapsed < RESPONSE_TIMEOUT_MS) {
      return
    }

    // Remove from pending
    this.pendingRequests.delete(interactionToken)

    // Send timeout error to Discord
    try {
      await editInteractionResponse(
        pending.appId,
        interactionToken,
        "⏱️ Request timed out. The Stellaris Companion app didn't respond in time. Please try again.",
        true
      )
    } catch (error) {
      console.error('Error sending timeout response:', error)
    }
  }

  /**
   * Handle Discord command from Worker
   * Called when a Discord slash command needs to be forwarded to Electron
   */
  async handleDiscordCommand(command: {
    interactionToken: string
    question: string
    userId: string
    guildId?: string
    channelId?: string
  }): Promise<void> {
    const electronSocket = this.getElectronSocket()
    if (!electronSocket) {
      throw new Error('APP_OFFLINE')
    }

    electronSocket.send(JSON.stringify({
      type: 'ask',
      interactionToken: command.interactionToken,
      question: command.question,
      userId: command.userId,
      guildId: command.guildId,
      channelId: command.channelId,
    }))
  }

  /**
   * Alarm handler for session TTL cleanup
   * Called when the alarm fires after SESSION_TTL_MS of inactivity
   */
  async alarm(): Promise<void> {
    const session = await this.ctx.storage.get<SessionData>('session')
    if (!session) {
      return
    }

    const now = Date.now()
    const timeSinceLastSeen = now - session.lastSeen

    if (timeSinceLastSeen >= SESSION_TTL_MS) {
      // Session expired - clean up
      console.log(`Session expired for user ${session.userId}, cleaning up`)
      await this.ctx.storage.delete('session')
      this.userId = null
      // Close any connected sockets
      const sockets = this.ctx.getWebSockets()
      for (const socket of sockets) {
        socket.close(4003, 'Session expired')
      }
    } else {
      // Session still valid - set alarm for remaining time
      const remainingTime = SESSION_TTL_MS - timeSinceLastSeen
      await this.ctx.storage.setAlarm(now + remainingTime)
    }
  }

  /**
   * Update last seen timestamp and reset TTL alarm
   */
  private async updateLastSeen(): Promise<void> {
    if (!this.userId) return

    const now = Date.now()
    await this.ctx.storage.put<SessionData>('session', {
      userId: this.userId,
      lastSeen: now,
    })

    // Set alarm for TTL check
    await this.ctx.storage.setAlarm(now + SESSION_TTL_MS)
  }
}
