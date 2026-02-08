/**
 * Authentication and Token Management
 *
 * Handles:
 * - Discord access token validation via Discord API
 * - Relay token minting (short-lived JWT for WebSocket auth)
 * - Relay token verification
 *
 * DISC-005: Relay token minted by Worker after validating Discord access_token via /users/@me
 */

/**
 * Discord user object (partial - only fields we need)
 */
export interface DiscordUser {
  id: string
  username: string
  discriminator: string
  avatar: string | null
}

/**
 * Relay token payload
 */
export interface RelayTokenPayload {
  userId: string
  username: string
  exp: number // Expiration timestamp (seconds since epoch)
  iat: number // Issued at timestamp (seconds since epoch)
}

/**
 * Result of Discord token validation
 */
export interface ValidationResult {
  success: boolean
  user?: DiscordUser
  error?: string
}

/**
 * Relay token expiration time (1 hour in seconds)
 * Electron can refresh by calling /relay/session again with a valid Discord token
 */
const RELAY_TOKEN_EXPIRY_SECONDS = 60 * 60 // 1 hour

/**
 * Validate a Discord access token by calling the Discord API
 *
 * Makes a request to /users/@me to verify the token is valid
 * and extract the authenticated user's information.
 *
 * @param accessToken - Discord OAuth access token
 * @returns ValidationResult with user info on success, or error on failure
 */
export async function validateDiscordAccessToken(
  accessToken: string
): Promise<ValidationResult> {
  try {
    const response = await fetch('https://discord.com/api/v10/users/@me', {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    })

    if (!response.ok) {
      const errorText = await response.text()
      return {
        success: false,
        error: `Discord API error: ${response.status} - ${errorText}`,
      }
    }

    const user = (await response.json()) as DiscordUser

    if (!user.id) {
      return {
        success: false,
        error: 'Invalid Discord response: missing user ID',
      }
    }

    return {
      success: true,
      user,
    }
  } catch (error) {
    return {
      success: false,
      error: `Failed to validate Discord token: ${error instanceof Error ? error.message : 'Unknown error'}`,
    }
  }
}

/**
 * Encode data to base64url (URL-safe base64)
 */
function base64urlEncode(data: string): string {
  const base64 = btoa(data)
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/**
 * Decode base64url to string
 */
function base64urlDecode(data: string): string {
  // Add back padding if needed
  let padded = data.replace(/-/g, '+').replace(/_/g, '/')
  const paddingNeeded = (4 - (padded.length % 4)) % 4
  padded += '='.repeat(paddingNeeded)
  return atob(padded)
}

/**
 * Create HMAC-SHA256 signature using Web Crypto API
 *
 * @param data - Data to sign
 * @param secret - Secret key for signing
 * @returns Base64url-encoded signature
 */
async function hmacSha256(data: string, secret: string): Promise<string> {
  const encoder = new TextEncoder()
  const keyData = encoder.encode(secret)
  const messageData = encoder.encode(data)

  const key = await crypto.subtle.importKey(
    'raw',
    keyData,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  )

  const signature = await crypto.subtle.sign('HMAC', key, messageData)
  const signatureArray = new Uint8Array(signature)
  const signatureString = String.fromCharCode(...signatureArray)
  return base64urlEncode(signatureString)
}

/**
 * Mint a short-lived relay token for WebSocket authentication
 *
 * Creates a JWT-like token signed with HMAC-SHA256.
 * Format: header.payload.signature (base64url encoded)
 *
 * Token expires in 1 hour. Electron can refresh by calling /relay/session
 * again with a valid Discord access token.
 *
 * @param user - Validated Discord user
 * @param signingSecret - Secret for signing the token (RELAY_SIGNING_SECRET)
 * @returns Signed relay token
 */
export async function mintRelayToken(
  user: DiscordUser,
  signingSecret: string
): Promise<string> {
  const now = Math.floor(Date.now() / 1000)

  // Header (simplified JWT header)
  const header = {
    alg: 'HS256',
    typ: 'JWT',
  }

  // Payload
  const payload: RelayTokenPayload = {
    userId: user.id,
    username: user.username,
    iat: now,
    exp: now + RELAY_TOKEN_EXPIRY_SECONDS,
  }

  // Encode header and payload
  const encodedHeader = base64urlEncode(JSON.stringify(header))
  const encodedPayload = base64urlEncode(JSON.stringify(payload))

  // Create signature
  const dataToSign = `${encodedHeader}.${encodedPayload}`
  const signature = await hmacSha256(dataToSign, signingSecret)

  // Return complete token
  return `${dataToSign}.${signature}`
}

/**
 * Result of relay token verification
 */
export interface VerifyResult {
  valid: boolean
  payload?: RelayTokenPayload
  error?: string
}

/**
 * Verify a relay token and extract its payload
 *
 * Checks:
 * 1. Token has valid format (3 parts)
 * 2. Signature matches
 * 3. Token is not expired
 *
 * @param token - Relay token to verify
 * @param signingSecret - Secret used for signing (RELAY_SIGNING_SECRET)
 * @returns VerifyResult with payload on success, or error on failure
 */
export async function verifyRelayToken(
  token: string,
  signingSecret: string
): Promise<VerifyResult> {
  try {
    // Split token into parts
    const parts = token.split('.')
    if (parts.length !== 3) {
      return { valid: false, error: 'Invalid token format' }
    }

    const [encodedHeader, encodedPayload, signature] = parts

    // Verify signature
    const dataToSign = `${encodedHeader}.${encodedPayload}`
    const expectedSignature = await hmacSha256(dataToSign, signingSecret)

    if (signature !== expectedSignature) {
      return { valid: false, error: 'Invalid signature' }
    }

    // Parse payload
    let payload: RelayTokenPayload
    try {
      payload = JSON.parse(base64urlDecode(encodedPayload))
    } catch {
      return { valid: false, error: 'Invalid payload format' }
    }

    // Check expiration
    const now = Math.floor(Date.now() / 1000)
    if (payload.exp && payload.exp < now) {
      return { valid: false, error: 'Token expired' }
    }

    // Check required fields
    if (!payload.userId) {
      return { valid: false, error: 'Missing userId in token' }
    }

    return { valid: true, payload }
  } catch (error) {
    return {
      valid: false,
      error: `Token verification failed: ${error instanceof Error ? error.message : 'Unknown error'}`,
    }
  }
}
