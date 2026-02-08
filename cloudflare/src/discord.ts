/**
 * Discord Integration Utilities
 *
 * Handles Discord-specific functionality:
 * - Signature verification for incoming interactions
 * - Interaction response helpers
 * - Discord API types and constants
 */

import { verifyKey } from 'discord-interactions'

/**
 * Discord Interaction Types
 * @see https://discord.com/developers/docs/interactions/receiving-and-responding#interaction-object-interaction-type
 */
export const InteractionType = {
  PING: 1,
  APPLICATION_COMMAND: 2,
  MESSAGE_COMPONENT: 3,
  APPLICATION_COMMAND_AUTOCOMPLETE: 4,
  MODAL_SUBMIT: 5,
} as const

/**
 * Discord Interaction Response Types
 * @see https://discord.com/developers/docs/interactions/receiving-and-responding#interaction-response-object-interaction-callback-type
 */
export const InteractionResponseType = {
  PONG: 1,
  CHANNEL_MESSAGE_WITH_SOURCE: 4,
  DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE: 5,
  DEFERRED_UPDATE_MESSAGE: 6,
  UPDATE_MESSAGE: 7,
  APPLICATION_COMMAND_AUTOCOMPLETE_RESULT: 8,
  MODAL: 9,
} as const

/**
 * Discord Message Flags
 * @see https://discord.com/developers/docs/resources/channel#message-object-message-flags
 */
export const MessageFlags = {
  EPHEMERAL: 64,
} as const

/**
 * Discord Interaction object (partial)
 */
export interface DiscordInteraction {
  id: string
  application_id: string
  type: number
  token: string
  data?: {
    id: string
    name: string
    options?: Array<{
      name: string
      type: number
      value: string | number | boolean
    }>
  }
  guild_id?: string
  channel_id?: string
  member?: {
    user: {
      id: string
      username: string
      discriminator: string
    }
  }
  user?: {
    id: string
    username: string
    discriminator: string
  }
}

/**
 * Verify Discord request signature
 *
 * Discord sends two headers for verification:
 * - X-Signature-Ed25519: The signature
 * - X-Signature-Timestamp: The timestamp
 *
 * These must be verified against the request body using the application's public key.
 *
 * @param request - The incoming request
 * @param publicKey - Discord application public key (from Developer Portal)
 * @returns Promise<boolean> - True if signature is valid
 */
export async function verifyDiscordSignature(
  request: Request,
  publicKey: string
): Promise<boolean> {
  const signature = request.headers.get('X-Signature-Ed25519')
  const timestamp = request.headers.get('X-Signature-Timestamp')

  if (!signature || !timestamp) {
    return false
  }

  // Clone request to read body without consuming it
  const body = await request.clone().text()

  // Use discord-interactions library for Ed25519 verification
  return verifyKey(body, signature, timestamp, publicKey)
}

/**
 * Create a deferred response for Discord interactions
 *
 * This immediately acknowledges the interaction, showing "Thinking..." in Discord.
 * The actual response must be sent later via webhook follow-up.
 *
 * @param ephemeral - If true, response is only visible to the user who triggered it
 * @returns Response - HTTP response with deferred message
 */
export function createDeferredResponse(ephemeral: boolean = true): Response {
  return new Response(
    JSON.stringify({
      type: InteractionResponseType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE,
      data: ephemeral ? { flags: MessageFlags.EPHEMERAL } : undefined,
    }),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  )
}

/**
 * Create a PONG response for Discord PING verification
 *
 * Discord sends a PING interaction when the Interactions Endpoint URL is configured.
 * We must respond with a PONG to verify the endpoint.
 *
 * @returns Response - HTTP response with PONG
 */
export function createPongResponse(): Response {
  return new Response(
    JSON.stringify({ type: InteractionResponseType.PONG }),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  )
}

/**
 * Create an error response for invalid signature
 *
 * @returns Response - 401 Unauthorized response
 */
export function createUnauthorizedResponse(): Response {
  return new Response('Invalid request signature', { status: 401 })
}

/**
 * Send a follow-up message to a Discord interaction (edits original)
 *
 * After deferring a response, use this to send the actual content.
 * Uses the webhook API with the interaction token.
 *
 * @param appId - Discord application ID
 * @param interactionToken - Token from the original interaction
 * @param content - Message content to send
 * @param ephemeral - If true, message is only visible to the user
 */
export async function sendFollowUp(
  appId: string,
  interactionToken: string,
  content: string,
  ephemeral: boolean = true
): Promise<Response> {
  const url = `https://discord.com/api/v10/webhooks/${appId}/${interactionToken}/messages/@original`

  return fetch(url, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      content,
      flags: ephemeral ? MessageFlags.EPHEMERAL : undefined,
    }),
  })
}

/**
 * Create a new follow-up message (for additional chunks)
 *
 * Unlike sendFollowUp/editInteractionResponse which edit the original deferred message,
 * this creates a NEW message in the channel. Use for sending additional chunks
 * when a response exceeds Discord's 2000 character limit.
 *
 * @param appId - Discord application ID
 * @param interactionToken - Token from the original interaction
 * @param content - Message content to send
 * @param ephemeral - If true, message is only visible to the user
 */
export async function createFollowUpMessage(
  appId: string,
  interactionToken: string,
  content: string,
  ephemeral: boolean = true
): Promise<Response> {
  const url = `https://discord.com/api/v10/webhooks/${appId}/${interactionToken}`

  return fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      content,
      flags: ephemeral ? MessageFlags.EPHEMERAL : undefined,
    }),
  })
}

/**
 * Edit the original interaction response
 *
 * DISC-006: Use interaction token for follow-up via webhook
 * PATCH /webhooks/{app_id}/{token}/messages/@original
 *
 * @param appId - Discord application ID
 * @param interactionToken - Token from the original interaction
 * @param content - New message content
 * @param ephemeral - If true, message is only visible to the user
 * @returns Promise<Response> - The fetch response
 */
export async function editInteractionResponse(
  appId: string,
  interactionToken: string,
  content: string,
  ephemeral: boolean = true
): Promise<Response> {
  const url = `https://discord.com/api/v10/webhooks/${appId}/${interactionToken}/messages/@original`

  return fetch(url, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      content,
      flags: ephemeral ? MessageFlags.EPHEMERAL : undefined,
    }),
  })
}

/**
 * Split a long response into multiple chunks for Discord's 2000 character limit
 *
 * @param text - The full response text
 * @param maxLength - Maximum length per chunk (default 2000 for Discord)
 * @returns Array of text chunks
 */
export function splitResponse(text: string, maxLength: number = 2000): string[] {
  if (text.length <= maxLength) {
    return [text]
  }

  const chunks: string[] = []
  let remaining = text

  while (remaining.length > 0) {
    if (remaining.length <= maxLength) {
      chunks.push(remaining)
      break
    }

    // Try to split on paragraph boundary
    let splitIndex = remaining.lastIndexOf('\n\n', maxLength)

    // Try sentence boundary if no paragraph
    if (splitIndex <= 0) {
      splitIndex = remaining.lastIndexOf('. ', maxLength)
      if (splitIndex > 0) splitIndex += 1 // Include the period
    }

    // Try word boundary if no sentence
    if (splitIndex <= 0) {
      splitIndex = remaining.lastIndexOf(' ', maxLength)
    }

    // Fall back to hard split
    if (splitIndex <= 0) {
      splitIndex = maxLength
    }

    chunks.push(remaining.slice(0, splitIndex).trim())
    remaining = remaining.slice(splitIndex).trim()
  }

  return chunks
}

/**
 * Get the user ID from a Discord interaction
 *
 * In guild context, user is nested under member.user
 * In DM context, user is directly on the interaction
 *
 * @param interaction - Discord interaction object
 * @returns User ID or undefined
 */
export function getUserId(interaction: DiscordInteraction): string | undefined {
  return interaction.member?.user?.id ?? interaction.user?.id
}

/**
 * Get the question text from a /ask command
 *
 * Extracts the value of the "question" option from the slash command.
 *
 * @param interaction - Discord interaction object
 * @returns Question text or undefined
 */
export function getQuestionFromAskCommand(
  interaction: DiscordInteraction
): string | undefined {
  const options = interaction.data?.options
  if (!options) return undefined

  const questionOption = options.find((opt) => opt.name === 'question')
  return questionOption?.value as string | undefined
}
