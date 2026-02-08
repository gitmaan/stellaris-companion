/**
 * Stellaris Companion Discord Relay - Worker Entry Point
 *
 * This Cloudflare Worker handles:
 * 1. Discord Interactions (slash commands via HTTP POST)
 * 2. WebSocket connections from Electron apps
 * 3. Relay token issuance for authenticated sessions
 *
 * Architecture:
 * - Discord sends slash commands to /discord/interaction
 * - Worker verifies signature, responds with deferred message
 * - Worker forwards question to user's Durable Object
 * - DO forwards via WebSocket to user's Electron app
 * - Electron calls local Python backend, returns response
 * - DO sends follow-up to Discord with response
 */

import { Hono } from 'hono'
import type { Context } from 'hono'

// Re-export Durable Object class for Cloudflare runtime
export { UserSession } from './durable-object'

// Import Discord utilities
import {
  verifyDiscordSignature,
  createDeferredResponse,
  createPongResponse,
  createUnauthorizedResponse,
  sendFollowUp,
  editInteractionResponse,
  InteractionType,
  InteractionResponseType,
  getUserId,
  getQuestionFromAskCommand,
  type DiscordInteraction,
} from './discord'

// Import auth utilities
import {
  validateDiscordAccessToken,
  mintRelayToken,
  verifyRelayToken,
} from './auth'

// DISC-003: Deferred response type for /ask command
// Discord requires response within 3 seconds - we use DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE (type 5)
// to immediately ACK, then follow up with actual response via webhook
const DEFERRED_RESPONSE_TYPE = InteractionResponseType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE // type 5

// Response timeout for Electron (30 seconds - Discord allows up to 15 minutes but we use shorter)
const RESPONSE_TIMEOUT_MS = 30000

/**
 * Environment bindings for the Worker
 */
export interface Env {
  // Durable Object namespace for user sessions
  USER_SESSIONS: DurableObjectNamespace

  // Discord application configuration
  DISCORD_APP_ID: string
  DISCORD_PUBLIC_KEY: string
  DISCORD_BOT_TOKEN?: string

  // Relay token signing secret
  RELAY_SIGNING_SECRET: string
}

// Create Hono app with environment typing
const app = new Hono<{ Bindings: Env }>()

/**
 * Health check endpoint
 */
app.get('/', (c: Context<{ Bindings: Env }>) => {
  return c.json({
    status: 'ok',
    service: 'stellaris-companion-relay',
    version: '1.0.0',
  })
})

/**
 * Discord Interactions endpoint
 * Receives slash commands from Discord as HTTP POST
 *
 * Flow:
 * 1. Verify Discord signature
 * 2. Handle PING (Discord verification)
 * 3. For APPLICATION_COMMAND, defer response and forward to DO
 * 4. DO forwards to Electron, receives response, sends follow-up to Discord
 */
app.post('/discord/interaction', async (c: Context<{ Bindings: Env }>) => {
  // Step 1: Verify Discord signature (DISC-002)
  const isValid = await verifyDiscordSignature(c.req.raw, c.env.DISCORD_PUBLIC_KEY)
  if (!isValid) {
    return createUnauthorizedResponse()
  }

  // Parse the interaction body
  const interaction = await c.req.json<DiscordInteraction>()

  // Step 2: Handle PING (Discord endpoint verification)
  if (interaction.type === InteractionType.PING) {
    return createPongResponse()
  }

  // Step 3: Handle APPLICATION_COMMAND (slash commands)
  if (interaction.type === InteractionType.APPLICATION_COMMAND) {
    const userId = getUserId(interaction)
    const question = getQuestionFromAskCommand(interaction)

    console.log(`[Worker] Slash command from userId: ${userId}, question: ${question?.substring(0, 50)}...`)

    if (!userId || !question) {
      // Invalid command - still need to respond with an error
      return createDeferredResponse(true)
    }

    // DISC-006: Wire up the full interaction flow
    // 1. Immediately defer the response (shows "Thinking..." in Discord)
    // 2. Use waitUntil to asynchronously forward to DO and handle response
    const deferredResponse = createDeferredResponse(true)

    // Get the Durable Object for this user
    // DISC-006: DO lookup via env.USER_SESSIONS.idFromName
    console.log(`[Worker] Looking up DO for userId: ${userId}`)
    const doId = c.env.USER_SESSIONS.idFromName(userId)
    const stub = c.env.USER_SESSIONS.get(doId)

    // Prepare command data for the DO
    const commandData = {
      interactionToken: interaction.token,
      question,
      userId,
      guildId: interaction.guild_id,
      channelId: interaction.channel_id,
      appId: c.env.DISCORD_APP_ID,
    }

    // Use waitUntil to process the command asynchronously
    // This allows us to return the deferred response immediately
    c.executionCtx.waitUntil(
      forwardCommandToDO(stub, commandData, c.env)
    )

    return deferredResponse
  }

  // Unknown interaction type
  return c.json({ error: 'Unknown interaction type' }, 400)
})

/**
 * Forward a Discord command to the user's Durable Object
 * Handles the async flow: DO -> Electron -> Discord webhook follow-up
 *
 * DISC-006: Full interaction flow implementation
 */
async function forwardCommandToDO(
  stub: DurableObjectStub,
  command: {
    interactionToken: string
    question: string
    userId: string
    guildId?: string
    channelId?: string
    appId: string
  },
  env: Env
): Promise<void> {
  try {
    // Forward command to DO via HTTP
    const response = await stub.fetch('https://do/forward', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        interactionToken: command.interactionToken,
        question: command.question,
        userId: command.userId,
        guildId: command.guildId,
        channelId: command.channelId,
        appId: command.appId,
      }),
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({})) as { error?: string }

      // DISC-006: Handle APP_OFFLINE error with friendly message
      if (errorData.error === 'APP_OFFLINE' || response.status === 503) {
        await editInteractionResponse(
          command.appId,
          command.interactionToken,
          "⚠️ Your Stellaris Companion app isn't connected. Please open the app and check the Discord connection in Settings.",
          true
        )
        return
      }

      // Other errors
      await editInteractionResponse(
        command.appId,
        command.interactionToken,
        "❌ Failed to process your request. Please try again.",
        true
      )
      return
    }

    // Success - the DO will handle sending the response to Discord
    // via the 'response' message from Electron
    console.log('Command forwarded to DO successfully')
  } catch (error) {
    console.error('Error forwarding command to DO:', error)

    // Send error response to Discord
    await editInteractionResponse(
      command.appId,
      command.interactionToken,
      "❌ An error occurred while processing your request. Please try again.",
      true
    )
  }
}

/**
 * Relay session endpoint
 * Exchanges Discord access token for a short-lived relay token
 *
 * DISC-005: Relay token minted by Worker after validating Discord access_token via /users/@me
 *
 * Flow:
 * 1. Extract Discord access token from Authorization header
 * 2. Validate token by calling Discord API (/users/@me)
 * 3. Extract verified user ID and username
 * 4. Mint short-lived relay token (JWT signed with RELAY_SIGNING_SECRET)
 * 5. Return relay_token for WebSocket authentication
 */
app.post('/relay/session', async (c: Context<{ Bindings: Env }>) => {
  // Step 1: Extract Discord access token from Authorization header
  const authHeader = c.req.header('Authorization')
  if (!authHeader?.startsWith('Bearer ')) {
    return c.json({ error: 'Missing or invalid Authorization header' }, 401)
  }

  const discordAccessToken = authHeader.slice(7) // Remove "Bearer "

  if (!discordAccessToken) {
    return c.json({ error: 'Empty access token' }, 401)
  }

  // Step 2: Validate Discord access token via Discord API (/users/@me)
  const validation = await validateDiscordAccessToken(discordAccessToken)

  if (!validation.success || !validation.user) {
    return c.json(
      { error: validation.error || 'Failed to validate Discord token' },
      401
    )
  }

  // Step 3: Check that RELAY_SIGNING_SECRET is configured
  if (!c.env.RELAY_SIGNING_SECRET) {
    console.error('RELAY_SIGNING_SECRET not configured')
    return c.json({ error: 'Server configuration error' }, 500)
  }

  // Step 4: Mint short-lived relay token
  const relayToken = await mintRelayToken(validation.user, c.env.RELAY_SIGNING_SECRET)

  // Step 5: Return relay token and user info
  return c.json({
    relay_token: relayToken,
    user: {
      id: validation.user.id,
      username: validation.user.username,
    },
    expires_in: 3600, // 1 hour in seconds
  })
})

/**
 * WebSocket upgrade endpoint
 * Electron apps connect here to receive forwarded Discord commands
 *
 * DISC-005: Require relay_token for WS upgrade; bind connection to verified Discord user ID
 *
 * Authentication flow:
 * 1. Client connects with Authorization header containing relay_token
 * 2. Worker verifies relay_token signature and expiration
 * 3. Worker extracts verified userId from token payload
 * 4. Worker routes to user's Durable Object by userId
 * 5. DO handles WebSocket upgrade and manages connection
 */
app.get('/ws', async (c: Context<{ Bindings: Env }>) => {
  // Check for WebSocket upgrade request
  const upgradeHeader = c.req.header('Upgrade')
  if (upgradeHeader !== 'websocket') {
    return c.json({ error: 'Expected WebSocket upgrade' }, 426)
  }

  // Extract relay token from Authorization header
  const authHeader = c.req.header('Authorization')
  if (!authHeader?.startsWith('Bearer ')) {
    return c.json({ error: 'Missing Authorization header' }, 401)
  }

  const token = authHeader.slice(7) // Remove "Bearer "

  if (!token) {
    return c.json({ error: 'Empty relay token' }, 401)
  }

  // Check that RELAY_SIGNING_SECRET is configured
  if (!c.env.RELAY_SIGNING_SECRET) {
    console.error('RELAY_SIGNING_SECRET not configured')
    return c.json({ error: 'Server configuration error' }, 500)
  }

  // Verify relay token signature and extract payload
  const verification = await verifyRelayToken(token, c.env.RELAY_SIGNING_SECRET)

  if (!verification.valid || !verification.payload) {
    return c.json(
      { error: verification.error || 'Invalid relay token' },
      401
    )
  }

  const userId = verification.payload.userId

  if (!userId) {
    return c.json({ error: 'Invalid token: no userId' }, 401)
  }

  console.log(`[Worker] WebSocket upgrade for userId: ${userId}`)

  // Get or create Durable Object for this user
  const doId = c.env.USER_SESSIONS.idFromName(userId)
  const stub = c.env.USER_SESSIONS.get(doId)

  console.log(`[Worker] Routing to DO with id: ${doId}`)

  // Forward the WebSocket upgrade request to the Durable Object
  // The DO will handle the actual WebSocket connection
  return stub.fetch(c.req.raw)
})

// Export the Hono app as the default fetch handler
export default app
