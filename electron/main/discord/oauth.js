const crypto = require('crypto')
const http = require('http')

function createDiscordOAuth({
  clientId,
  shell,
  store,
  getSecret,
  setSecret,
  secretKeys,
  onConnected,
}) {
  if (!shell) throw new Error('createDiscordOAuth: shell is required')
  if (!store) throw new Error('createDiscordOAuth: store is required')
  if (typeof getSecret !== 'function') throw new Error('createDiscordOAuth: getSecret() is required')
  if (typeof setSecret !== 'function') throw new Error('createDiscordOAuth: setSecret() is required')
  if (!secretKeys?.accessToken || !secretKeys?.refreshToken) throw new Error('createDiscordOAuth: secretKeys.accessToken/refreshToken are required')

  // State for OAuth flow
  let oauthCallbackServer = null
  let oauthCodeVerifier = null

  function setOnConnected(next) {
    onConnected = next
  }

  /**
   * Generate a random code_verifier for PKCE (43-128 characters).
   * Uses base64url encoding per RFC 7636.
   * @returns {string} Code verifier string
   */
  function generateCodeVerifier() {
    // 32 bytes -> 43 base64url characters (per RFC 7636, must be 43-128 chars)
    return crypto.randomBytes(32).toString('base64url')
  }

  /**
   * Generate code_challenge from code_verifier using S256 method.
   * code_challenge = base64url(sha256(code_verifier))
   * @param {string} codeVerifier - The code verifier
   * @returns {string} Code challenge string
   */
  function generateCodeChallenge(codeVerifier) {
    return crypto.createHash('sha256').update(codeVerifier).digest('base64url')
  }

  /**
   * Store Discord OAuth tokens securely via safeStorage.
   *
   * @param {Object} tokens - Token data from exchangeCodeForTokens
   */
  function storeDiscordTokens(tokens) {
    setSecret(secretKeys.accessToken, tokens.accessToken)
    if (tokens.refreshToken) {
      setSecret(secretKeys.refreshToken, tokens.refreshToken)
    }

    store.set('discordUserId', tokens.userId)
    store.set('discordUsername', tokens.username)
    store.set('discordTokenExpiry', new Date(tokens.expiresAt).toISOString())
  }

  /**
   * Get stored Discord OAuth tokens.
   *
   * @returns {Object|null} Token data or null if not connected
   */
  function getDiscordTokens() {
    const accessToken = getSecret(secretKeys.accessToken)
    const refreshToken = getSecret(secretKeys.refreshToken)
    const userId = store.get('discordUserId')
    const username = store.get('discordUsername')
    const expiryStr = store.get('discordTokenExpiry')

    if (!accessToken || !userId) {
      return null
    }

    return {
      accessToken,
      refreshToken,
      userId,
      username,
      expiresAt: expiryStr ? new Date(expiryStr).getTime() : null,
    }
  }

  /**
   * Clear Discord OAuth tokens (disconnect).
   */
  function clearDiscordTokens() {
    setSecret(secretKeys.accessToken, null)
    setSecret(secretKeys.refreshToken, null)
    store.delete('discordUserId')
    store.delete('discordUsername')
    store.delete('discordTokenExpiry')
  }

  /**
   * Check if Discord is connected (has valid tokens).
   *
   * @returns {Promise<Object>} Connection status with user info if connected
   */
  async function getDiscordConnectionStatus() {
    const tokens = await getDiscordTokens()

    if (!tokens) {
      return { connected: false }
    }

    // Check if token is expired (with 5 minute buffer)
    const now = Date.now()
    const isExpired = tokens.expiresAt && (tokens.expiresAt - 5 * 60 * 1000) < now

    if (isExpired && tokens.refreshToken) {
      // Token expired but we have refresh token - could refresh
      // For now, mark as needing refresh
      return {
        connected: true,
        needsRefresh: true,
        userId: tokens.userId,
        username: tokens.username,
      }
    }

    return {
      connected: !isExpired,
      userId: tokens.userId,
      username: tokens.username,
    }
  }

  /**
   * Exchange authorization code for tokens.
   * Uses PKCE - no client_secret required.
   *
   * @param {string} code - Authorization code from Discord
   * @param {string} redirectUri - The redirect URI used in the auth request
   * @param {string} codeVerifier - The PKCE code verifier
   * @returns {Promise<Object>} Token response with access_token, refresh_token, user info
   */
  async function exchangeCodeForTokens(code, redirectUri, codeVerifier) {
    // Exchange code for tokens at Discord's token endpoint
    // PKCE flow: include code_verifier, no client_secret
    const tokenResponse = await fetch('https://discord.com/api/oauth2/token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        client_id: clientId,
        grant_type: 'authorization_code',
        code: code,
        redirect_uri: redirectUri,
        code_verifier: codeVerifier,
      }),
    })

    if (!tokenResponse.ok) {
      const errorText = await tokenResponse.text()
      throw new Error(`Token exchange failed: ${tokenResponse.status} - ${errorText}`)
    }

    const tokenData = await tokenResponse.json()

    if (!tokenData.access_token) {
      throw new Error('No access token in response')
    }

    // Get user info to verify the token and get user details
    const userResponse = await fetch('https://discord.com/api/v10/users/@me', {
      headers: {
        Authorization: `Bearer ${tokenData.access_token}`,
      },
    })

    if (!userResponse.ok) {
      throw new Error(`Failed to fetch user info: ${userResponse.status}`)
    }

    const userData = await userResponse.json()

    return {
      accessToken: tokenData.access_token,
      refreshToken: tokenData.refresh_token,
      expiresIn: tokenData.expires_in,
      expiresAt: Date.now() + (tokenData.expires_in * 1000),
      userId: userData.id,
      username: userData.username,
    }
  }

  /**
   * Start the Discord OAuth PKCE flow.
   * Opens a browser for user authorization and catches the callback.
   *
   * DISC-007: OAuth PKCE uses code_verifier/code_challenge, localhost callback, no client_secret
   *
   * @returns {Promise<Object>} Result with tokens or error
   */
  async function startDiscordOAuth() {
    // Check if Discord client ID is configured
    if (!clientId) {
      return { success: false, error: 'Discord client ID not configured' }
    }

    // Close any existing callback server
    if (oauthCallbackServer) {
      try {
        oauthCallbackServer.close()
      } catch (e) {
        // ignore
      }
      oauthCallbackServer = null
    }

    // Generate PKCE values
    oauthCodeVerifier = generateCodeVerifier()
    const codeChallenge = generateCodeChallenge(oauthCodeVerifier)

    return new Promise((resolve) => {
      // Create localhost HTTP server for callback
      oauthCallbackServer = http.createServer(async (req, res) => {
        // Parse the callback URL
        const url = new URL(req.url, `http://127.0.0.1`)

        if (url.pathname === '/callback') {
          const code = url.searchParams.get('code')
          const error = url.searchParams.get('error')
          const errorDescription = url.searchParams.get('error_description')

          // Send success page to user's browser
          res.writeHead(200, { 'Content-Type': 'text/html' })
          if (error) {
            res.end(`
            <!DOCTYPE html>
            <html>
            <head><title>Stellaris Companion</title></head>
            <body style="font-family: system-ui; padding: 40px; text-align: center;">
              <h1>❌ Authorization Failed</h1>
              <p>${errorDescription || error}</p>
              <p>You can close this window.</p>
            </body>
            </html>
          `)
            oauthCallbackServer.close()
            oauthCallbackServer = null
            resolve({ success: false, error: errorDescription || error })
            return
          }

          if (!code) {
            res.end(`
            <!DOCTYPE html>
            <html>
            <head><title>Stellaris Companion</title></head>
            <body style="font-family: system-ui; padding: 40px; text-align: center;">
              <h1>❌ Authorization Failed</h1>
              <p>No authorization code received.</p>
              <p>You can close this window.</p>
            </body>
            </html>
          `)
            oauthCallbackServer.close()
            oauthCallbackServer = null
            resolve({ success: false, error: 'No authorization code received' })
            return
          }

          // Exchange code for tokens
          const port = oauthCallbackServer.address().port
          const redirectUri = `http://127.0.0.1:${port}/callback`

          try {
            const tokens = await exchangeCodeForTokens(code, redirectUri, oauthCodeVerifier)

            res.end(`
            <!DOCTYPE html>
            <html>
            <head><title>Stellaris Companion</title></head>
            <body style="font-family: system-ui; padding: 40px; text-align: center;">
              <h1>✅ Connected to Discord!</h1>
              <p>You can close this window and return to Stellaris Companion.</p>
              <script>setTimeout(() => window.close(), 2000)</script>
            </body>
            </html>
          `)

            oauthCallbackServer.close()
            oauthCallbackServer = null
            oauthCodeVerifier = null

            // Store tokens securely
            await storeDiscordTokens(tokens)

            // Start Discord relay connection (DISC-008)
            // We use setImmediate to allow the OAuth flow to complete first
            setImmediate(async () => {
              if (typeof onConnected === 'function') {
                await onConnected()
              }
            })

            resolve({
              success: true,
              userId: tokens.userId,
              username: tokens.username,
            })
          } catch (e) {
            res.end(`
            <!DOCTYPE html>
            <html>
            <head><title>Stellaris Companion</title></head>
            <body style="font-family: system-ui; padding: 40px; text-align: center;">
              <h1>❌ Authorization Failed</h1>
              <p>${e.message}</p>
              <p>You can close this window.</p>
            </body>
            </html>
          `)
            oauthCallbackServer.close()
            oauthCallbackServer = null
            resolve({ success: false, error: e.message })
          }
        } else {
          // Unknown path
          res.writeHead(404)
          res.end('Not found')
        }
      })

      // Listen on a random available port
      oauthCallbackServer.listen(0, '127.0.0.1', () => {
        const port = oauthCallbackServer.address().port
        const redirectUri = encodeURIComponent(`http://127.0.0.1:${port}/callback`)

        // Build Discord OAuth authorize URL with PKCE
        const authUrl =
          `https://discord.com/oauth2/authorize?` +
          `client_id=${clientId}` +
          `&response_type=code` +
          `&redirect_uri=${redirectUri}` +
          `&scope=identify%20guilds` +
          `&code_challenge=${codeChallenge}` +
          `&code_challenge_method=S256`

        console.log(`Discord OAuth: Opening browser for authorization (port ${port})`)

        // Open the authorization URL in the user's default browser
        shell.openExternal(authUrl)
      })

      oauthCallbackServer.on('error', (err) => {
        console.error('OAuth callback server error:', err)
        resolve({ success: false, error: `Server error: ${err.message}` })
      })

      // Timeout after 5 minutes
      setTimeout(() => {
        if (oauthCallbackServer) {
          oauthCallbackServer.close()
          oauthCallbackServer = null
          resolve({ success: false, error: 'Authorization timeout' })
        }
      }, 5 * 60 * 1000)
    })
  }

  // =============================================================================
  // Discord Token Refresh Flow (DISC-011)
  // =============================================================================

  /**
   * Refresh the Discord access token using the refresh token.
   * Calls Discord's token endpoint with grant_type=refresh_token.
   *
   * DISC-011: Token refresh flow - no client_secret required for PKCE public clients
   *
   * @param {string} refreshToken - The OAuth refresh token
   * @returns {Promise<Object>} New token data with access_token, refresh_token, expiry
   * @throws {Error} If refresh fails (token revoked, invalid, etc.)
   */
  async function refreshAccessToken(refreshToken) {
    if (!refreshToken) {
      throw new Error('No refresh token provided')
    }

    if (!clientId) {
      throw new Error('Discord client ID not configured')
    }

    console.log('Discord OAuth: refreshing access token...')

    // Call Discord token endpoint with grant_type=refresh_token
    // PKCE public clients don't need client_secret
    const tokenResponse = await fetch('https://discord.com/api/oauth2/token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        client_id: clientId,
        grant_type: 'refresh_token',
        refresh_token: refreshToken,
      }),
    })

    if (!tokenResponse.ok) {
      const errorText = await tokenResponse.text()
      console.error('Discord OAuth: token refresh failed:', tokenResponse.status, errorText)
      throw new Error(`Token refresh failed: ${tokenResponse.status} - ${errorText}`)
    }

    const tokenData = await tokenResponse.json()

    if (!tokenData.access_token) {
      throw new Error('No access token in refresh response')
    }

    console.log('Discord OAuth: token refreshed successfully')

    // Get user info to verify the new token and update user details
    const userResponse = await fetch('https://discord.com/api/v10/users/@me', {
      headers: {
        Authorization: `Bearer ${tokenData.access_token}`,
      },
    })

    if (!userResponse.ok) {
      throw new Error(`Failed to fetch user info after refresh: ${userResponse.status}`)
    }

    const userData = await userResponse.json()

    return {
      accessToken: tokenData.access_token,
      refreshToken: tokenData.refresh_token || refreshToken, // Discord may return new refresh token
      expiresIn: tokenData.expires_in,
      expiresAt: Date.now() + (tokenData.expires_in * 1000),
      userId: userData.id,
      username: userData.username,
    }
  }

  /**
   * Ensure we have valid Discord tokens, refreshing if necessary.
   * Checks if access token expires within 5 minutes and refreshes proactively.
   *
   * DISC-011: Check token expiry before each reconnect attempt
   *
   * @returns {Promise<Object>} Valid token data
   * @throws {Error} If not authenticated or refresh fails
   */
  async function ensureValidTokens() {
    const tokens = await getDiscordTokens()

    if (!tokens) {
      throw new Error('NOT_AUTHENTICATED')
    }

    if (!tokens.accessToken) {
      throw new Error('NOT_AUTHENTICATED')
    }

    // Check if access token expires within 5 minutes
    const expiryBuffer = 5 * 60 * 1000 // 5 minutes in milliseconds
    const needsRefresh = tokens.expiresAt && tokens.expiresAt < (Date.now() + expiryBuffer)

    if (needsRefresh) {
      console.log('Discord OAuth: access token expiring soon, attempting refresh...')

      if (!tokens.refreshToken) {
        // No refresh token - need full re-auth
        await clearDiscordTokens()
        throw new Error('TOKEN_EXPIRED')
      }

      try {
        const newTokens = await refreshAccessToken(tokens.refreshToken)
        await storeDiscordTokens(newTokens)
        console.log('Discord OAuth: tokens refreshed and stored')
        return newTokens
      } catch (error) {
        // Refresh token also expired or revoked
        console.error('Discord OAuth: refresh failed:', error.message)
        await clearDiscordTokens()
        throw new Error('TOKEN_EXPIRED')
      }
    }

    // Token is still valid
    return tokens
  }

  return {
    startDiscordOAuth,
    getDiscordTokens,
    clearDiscordTokens,
    getDiscordConnectionStatus,
    ensureValidTokens,
    setOnConnected,
  }
}

module.exports = {
  createDiscordOAuth,
}

