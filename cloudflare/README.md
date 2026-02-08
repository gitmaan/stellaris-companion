# Stellaris Companion Discord Relay

Cloudflare Worker + Durable Objects relay for Discord integration. This relay forwards Discord slash commands to users' local Electron apps via WebSocket.

> **Note**: This documentation is for project maintainers. End users don't need to deploy this - they just click "Connect with Discord" in the Electron app.

## Architecture

```
Discord ─── HTTP POST ───▶ Cloudflare Worker ─── WebSocket ───▶ Electron App
                              │                                      │
                              ▼                                      ▼
                        Durable Object                         Python Backend
                        (per user)                              (local LLM)
```

- **Cloudflare Worker**: Receives Discord interactions, verifies signatures, routes to DOs
- **Durable Objects**: One per authenticated user, maintains WebSocket to Electron
- **Electron App**: Connects via WebSocket, receives questions, calls local Python backend
- **Python Backend**: Processes questions with user's Gemini API key (stays local)

## Prerequisites

1. **Cloudflare Account** with Workers + Durable Objects enabled
2. **Discord Application** configured for interactions
3. **Wrangler CLI** installed: `npm install -g wrangler`

## Discord Application Setup

### 1. Create Discord Application

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name (e.g., "Stellaris Companion")
3. Save the following values:
   - **Application ID** (on General Information page)
   - **Public Key** (on General Information page)

### 2. Configure OAuth2

1. Go to **OAuth2** → **General**
2. **Important**: Check "Public Client" - required for PKCE flow without client_secret
3. Add redirect URI: `http://127.0.0.1:*/callback` (Electron's localhost callback)

### 3. Configure Bot (Optional)

If you want the bot to appear in servers:

1. Go to **Bot** section
2. Click "Add Bot"
3. Under Privileged Gateway Intents, you do NOT need any special intents (slash commands only)
4. Copy the **Bot Token** (only needed if you want proactive messages)

### 4. Register Slash Commands

Register the `/ask` command using the Discord API:

```bash
# Set your bot token
export DISCORD_BOT_TOKEN="your-bot-token"
export DISCORD_APP_ID="your-app-id"

# Register /ask command globally
curl -X POST \
  "https://discord.com/api/v10/applications/${DISCORD_APP_ID}/commands" \
  -H "Authorization: Bot ${DISCORD_BOT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ask",
    "description": "Ask your Stellaris advisor a question",
    "type": 1,
    "options": [
      {
        "name": "question",
        "description": "Your question for the advisor",
        "type": 3,
        "required": true
      }
    ]
  }'
```

### 5. Generate Invite Link

Create an invite link for users to add the bot to their servers:

```
https://discord.com/oauth2/authorize?client_id=YOUR_APP_ID&scope=applications.commands+bot&permissions=2048
```

Permissions:
- `applications.commands` - Required for slash commands
- `bot` - Required for bot presence
- Permission `2048` = Send Messages

## Cloudflare Deployment

### 1. Install Dependencies

```bash
cd cloudflare
npm install
```

### 2. Configure wrangler.toml

Update `wrangler.toml` with your Discord Application ID:

```toml
[vars]
DISCORD_APP_ID = "your-discord-application-id"
```

### 3. Set Secrets

Required secrets (set via `wrangler secret put`):

```bash
# Discord Public Key - from Developer Portal → General Information
wrangler secret put DISCORD_PUBLIC_KEY
# Paste your public key when prompted

# Relay Signing Secret - generate a random 32+ character string
# Used to sign short-lived relay tokens for WebSocket authentication
wrangler secret put RELAY_SIGNING_SECRET
# Example: openssl rand -base64 32

# (Optional) Discord Bot Token - only needed for proactive messages
wrangler secret put DISCORD_BOT_TOKEN
# Paste your bot token if you have one
```

### 4. Deploy

```bash
# Deploy to Cloudflare
wrangler deploy
```

This outputs your Worker URL, e.g., `https://stellaris-companion-relay.your-subdomain.workers.dev`

### 5. Configure Discord Interactions URL

1. Go to Discord Developer Portal → Your App → General Information
2. Set **Interactions Endpoint URL** to:
   ```
   https://stellaris-companion-relay.your-subdomain.workers.dev/discord/interaction
   ```
3. Discord will send a PING to verify - the Worker responds with PONG automatically

## Development

### Local Development

```bash
cd cloudflare

# Start local dev server
npm run dev
# Worker available at http://localhost:8787
```

**Note**: Discord interactions require HTTPS, so local dev is mainly for testing:
- `/` - Health check endpoint
- `/relay/session` - Token exchange endpoint
- `/ws` - WebSocket endpoint (for Electron connection)

### Testing the WebSocket

```bash
# Get a relay token (needs valid Discord access token)
curl -X POST http://localhost:8787/relay/session \
  -H "Authorization: Bearer <discord-access-token>" \
  -H "Content-Type: application/json"

# Connect via wscat (npm install -g wscat)
wscat -c "ws://localhost:8787/ws" -H "Authorization: Bearer <relay-token>"
```

### Type Checking

```bash
npm run typecheck
```

### View Logs

```bash
# Real-time logs from production
npm run tail
```

## API Endpoints

### `GET /`
Health check. Returns:
```json
{ "status": "ok", "service": "stellaris-companion-relay", "version": "1.0.0" }
```

### `POST /discord/interaction`
Discord Interactions endpoint. Receives slash commands from Discord.
- Verifies signature using `DISCORD_PUBLIC_KEY`
- Returns 401 if signature invalid
- Handles PING with PONG for endpoint verification
- Defers response for `/ask` commands, forwards to Durable Object

### `POST /relay/session`
Exchange Discord access token for relay token.

**Request**:
```
Authorization: Bearer <discord-access-token>
```

**Response**:
```json
{
  "relay_token": "eyJ...",
  "user": { "id": "123", "username": "player" },
  "expires_in": 3600
}
```

### `GET /ws`
WebSocket upgrade endpoint for Electron apps.

**Request**:
```
Upgrade: websocket
Authorization: Bearer <relay-token>
```

**WebSocket Messages**:

From Cloudflare to Electron:
```json
{ "type": "ask", "interactionToken": "...", "question": "...", "userId": "...", "guildId": "...", "channelId": "..." }
```

From Electron to Cloudflare:
```json
{ "type": "auth", "userId": "..." }
{ "type": "response", "interactionToken": "...", "text": "..." }
{ "type": "disconnect" }
```

## Environment Variables

### Required Secrets

| Secret | Description |
|--------|-------------|
| `DISCORD_PUBLIC_KEY` | Discord application public key for signature verification |
| `RELAY_SIGNING_SECRET` | Secret for signing relay tokens (32+ random chars) |

### Optional Secrets

| Secret | Description |
|--------|-------------|
| `DISCORD_BOT_TOKEN` | Bot token for proactive messages (not needed for basic /ask) |

### Configuration Variables

Set in `wrangler.toml`:

| Variable | Description |
|----------|-------------|
| `DISCORD_APP_ID` | Discord application ID |

## Cost Considerations

The relay is designed to be cost-efficient:

1. **Hibernatable WebSockets**: Durable Objects sleep when idle, billing only for active compute
2. **Stateless Worker**: Worker handles Discord signatures and routes to DOs - no persistent state
3. **Minimal Storage**: Only session metadata stored (userId, lastSeen)

**Main cost factors**:
- DO requests (WebSocket messages count as requests)
- DO wall-clock time while processing
- Storage for session metadata

See [Cloudflare Workers Pricing](https://developers.cloudflare.com/workers/platform/pricing/) for current rates.

## Troubleshooting

### "Invalid request signature" from Discord

1. Verify `DISCORD_PUBLIC_KEY` is set correctly
2. Check the key matches your Discord application's public key
3. Ensure no whitespace in the secret

### Worker not responding to Discord

1. Check Interactions Endpoint URL is correct in Discord Developer Portal
2. Verify Worker is deployed: `wrangler deploy`
3. Check logs: `npm run tail`

### WebSocket connection fails

1. Verify relay token is valid (not expired)
2. Check `RELAY_SIGNING_SECRET` is set
3. Ensure Electron is sending correct Authorization header

### Electron not receiving commands

1. Check WebSocket connection state in Electron
2. Verify user is authenticated with correct Discord account
3. Check DO logs for errors

## Security

- **Signature Verification**: All Discord interactions verified using Ed25519
- **Token-based Auth**: WebSocket connections require valid relay tokens
- **No Stored Secrets**: Discord access tokens never stored on Cloudflare
- **Short-lived Tokens**: Relay tokens expire after 1 hour
- **User Isolation**: Each user has their own Durable Object instance
