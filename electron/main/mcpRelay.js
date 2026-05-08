const fs = require('fs')
const os = require('os')
const path = require('path')
const { spawn } = require('child_process')

const SERVER_NAME = 'stellaris-companion'
const LEGACY_SERVER_NAMES = [SERVER_NAME, 'stellaris-companion-dev']
const MCPB_SETTINGS_MATCH = /^local\.mcpb\..*stellaris-companion.*mcp-relay.*\.json$/

function shellQuote(value) {
  const text = String(value)
  if (/^[A-Za-z0-9_/:=.,@%+-]+$/.test(text)) return text
  return `'${text.replace(/'/g, `'\\''`)}'`
}

function jsonPretty(value) {
  return JSON.stringify(value, null, 2)
}

function getClaudeDesktopConfigPath() {
  const home = os.homedir()
  if (process.platform === 'darwin') {
    return path.join(home, 'Library', 'Application Support', 'Claude', 'claude_desktop_config.json')
  }
  if (process.platform === 'win32') {
    const appData = process.env.APPDATA || path.join(home, 'AppData', 'Roaming')
    return path.join(appData, 'Claude', 'claude_desktop_config.json')
  }
  return path.join(home, '.config', 'Claude', 'claude_desktop_config.json')
}

function getClaudeMcpbSettingsDir() {
  const home = os.homedir()
  if (process.platform === 'darwin') {
    return path.join(home, 'Library', 'Application Support', 'Claude', 'Claude Extensions Settings')
  }
  if (process.platform === 'win32') {
    const appData = process.env.APPDATA || path.join(home, 'AppData', 'Roaming')
    return path.join(appData, 'Claude', 'Claude Extensions Settings')
  }
  return path.join(home, '.config', 'Claude', 'Claude Extensions Settings')
}

function readJsonFile(filePath) {
  if (!fs.existsSync(filePath)) return null
  const raw = fs.readFileSync(filePath, 'utf8')
  if (!raw.trim()) return {}
  return JSON.parse(raw)
}

function normalizeConfigEnv(env) {
  const normalized = {}
  Object.entries(env || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value) !== '') {
      normalized[key] = String(value)
    }
  })
  return normalized
}

function resolveExecutable(command) {
  if (!command || typeof command !== 'string') return command
  if (path.isAbsolute(command) || command.includes(path.sep)) return command
  const pathEnv = process.env.PATH || ''
  const extensions = process.platform === 'win32'
    ? (process.env.PATHEXT || '.EXE;.CMD;.BAT').split(';')
    : ['']
  for (const directory of pathEnv.split(path.delimiter)) {
    if (!directory) continue
    for (const extension of extensions) {
      const candidate = path.join(directory, `${command}${extension}`)
      if (fs.existsSync(candidate)) return candidate
    }
  }
  return command
}

function sameArray(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b)) return false
  if (a.length !== b.length) return false
  return a.every((value, index) => value === b[index])
}

function serverLooksCurrent(server, target) {
  if (!server || typeof server !== 'object') return false
  return server.command === target.command && sameArray(server.args || [], target.args || [])
}

function samePath(left, right) {
  if (!left || !right) return false
  return path.resolve(String(left)) === path.resolve(String(right))
}

function buildCodexCommand(config) {
  const envArgs = Object.entries(config.env || {})
    .map(([key, value]) => `--env ${shellQuote(`${key}=${value}`)}`)
    .join(' ')
  const command = [config.command, ...(config.args || [])].map(shellQuote).join(' ')
  return ['codex mcp add', envArgs, SERVER_NAME, '--', command].filter(Boolean).join(' ')
}

function buildClaudeCodeCommand(config) {
  const typedConfig = {
    type: 'stdio',
    command: config.command,
    args: config.args || [],
    env: config.env || {},
  }
  return `claude mcp add-json --scope user ${SERVER_NAME} ${shellQuote(JSON.stringify(typedConfig))}`
}

function createMcpRelayService({ app, getPythonPath, getResolvedLanguage }) {
  if (!app) throw new Error('createMcpRelayService: app is required')
  if (typeof getPythonPath !== 'function') throw new Error('createMcpRelayService: getPythonPath is required')
  if (typeof getResolvedLanguage !== 'function') throw new Error('createMcpRelayService: getResolvedLanguage is required')

  function getRepoRoot() {
    return path.resolve(__dirname, '..', '..')
  }

  function getCurrentAppPath() {
    if (!app.isPackaged) return getRepoRoot()
    if (process.platform === 'darwin') {
      return path.resolve(path.dirname(process.execPath), '..', '..')
    }
    return path.dirname(process.execPath)
  }

  function buildLaunchConfig() {
    const dbPath = path.join(app.getPath('userData'), 'stellaris_history.db')
    const logDir = path.join(app.getPath('userData'), 'logs')
    const language = getResolvedLanguage()
    const command = resolveExecutable(getPythonPath())
    const args = app.isPackaged
      ? ['--mcp', '--db-path', dbPath, '--language', language]
      : ['-m', 'backend.electron_main', '--mcp', '--db-path', dbPath, '--language', language]
    const env = normalizeConfigEnv({
      STELLARIS_DB_PATH: dbPath,
      STELLARIS_LOG_DIR: logDir,
      PYTHONPATH: app.isPackaged ? undefined : getRepoRoot(),
    })
    const serverConfig = {
      command,
      args,
      env,
    }
    return {
      serverName: SERVER_NAME,
      dbPath,
      databaseExists: fs.existsSync(dbPath),
      logDir,
      language,
      command,
      args,
      env,
      serverConfig,
    }
  }

  function buildSnippets(config) {
    const desktopConfig = {
      mcpServers: {
        [SERVER_NAME]: config.serverConfig,
      },
    }
    return {
      claudeDesktop: jsonPretty(desktopConfig),
      claudeCode: buildClaudeCodeCommand(config.serverConfig),
      codex: buildCodexCommand(config.serverConfig),
      genericJson: jsonPretty(desktopConfig),
    }
  }

  function getClaudeMcpbStatus() {
    const settingsDir = getClaudeMcpbSettingsDir()
    const status = {
      settingsDir,
      configPath: null,
      configExists: fs.existsSync(settingsDir),
      configured: false,
      current: false,
      enabled: false,
      appPath: null,
      error: null,
    }

    try {
      if (!status.configExists) return status
      const names = fs.readdirSync(settingsDir).filter((name) => MCPB_SETTINGS_MATCH.test(name))
      if (names.length === 0) return status

      status.configPath = path.join(settingsDir, names[0])
      const existing = readJsonFile(status.configPath) || {}
      const userConfig = existing.userConfig && typeof existing.userConfig === 'object'
        ? existing.userConfig
        : {}
      status.configured = true
      status.enabled = existing.isEnabled !== false
      status.appPath = typeof userConfig.stellaris_companion_path === 'string'
        ? userConfig.stellaris_companion_path
        : null
      status.current = status.enabled && samePath(status.appPath, getCurrentAppPath())
      return status
    } catch (error) {
      status.error = error instanceof Error ? error.message : String(error)
      return status
    }
  }

  function getClaudeDesktopConfigStatus(config) {
    const configPath = getClaudeDesktopConfigPath()
    const status = {
      configPath,
      configExists: fs.existsSync(configPath),
      configured: false,
      serverName: null,
      error: null,
    }

    try {
      const existing = readJsonFile(configPath)
      const servers = existing?.mcpServers && typeof existing.mcpServers === 'object'
        ? existing.mcpServers
        : {}
      for (const name of LEGACY_SERVER_NAMES) {
        if (servers[name]) {
          status.configured = true
          status.serverName = name
          status.current = serverLooksCurrent(servers[name], config.serverConfig)
          return status
        }
      }
      status.current = false
      return status
    } catch (error) {
      status.error = error instanceof Error ? error.message : String(error)
      return status
    }
  }

  function getClaudeDesktopStatus(config) {
    const desktopConfig = getClaudeDesktopConfigStatus(config)
    const mcpb = getClaudeMcpbStatus()
    const configured = desktopConfig.configured || mcpb.configured
    const current = Boolean(desktopConfig.current || mcpb.current)

    return {
      ...desktopConfig,
      configPath: desktopConfig.configured
        ? desktopConfig.configPath
        : (mcpb.configPath || desktopConfig.configPath),
      configExists: desktopConfig.configExists || mcpb.configExists,
      configured,
      current,
      serverName: desktopConfig.serverName || (mcpb.configured ? 'stellaris-companion-mcp-relay' : null),
      error: desktopConfig.error || mcpb.error,
      mcpb,
    }
  }

  function getStatus() {
    const config = buildLaunchConfig()
    return {
      ...config,
      snippets: buildSnippets(config),
      claudeDesktop: getClaudeDesktopStatus(config),
    }
  }

  async function installClaudeDesktopConfig() {
    const config = buildLaunchConfig()
    const configPath = getClaudeDesktopConfigPath()
    let existing = {}

    try {
      existing = readJsonFile(configPath) || {}
    } catch (error) {
      return {
        success: false,
        error: `Claude Desktop config is not valid JSON: ${error instanceof Error ? error.message : String(error)}`,
        configPath,
      }
    }

    if (!existing || typeof existing !== 'object' || Array.isArray(existing)) {
      return {
        success: false,
        error: 'Claude Desktop config must be a JSON object.',
        configPath,
      }
    }

    const next = {
      ...existing,
      mcpServers: {
        ...(existing.mcpServers && typeof existing.mcpServers === 'object' ? existing.mcpServers : {}),
        [SERVER_NAME]: config.serverConfig,
      },
    }

    try {
      fs.mkdirSync(path.dirname(configPath), { recursive: true })
      fs.writeFileSync(configPath, `${jsonPretty(next)}\n`, 'utf8')
      return {
        success: true,
        configPath,
        serverName: SERVER_NAME,
        status: getStatus(),
      }
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error),
        configPath,
      }
    }
  }

  function runHealthCheck() {
    const config = buildLaunchConfig()
    return new Promise((resolve) => {
      const startedAt = Date.now()
      const childEnv = {
        ...process.env,
        ...config.env,
      }
      const child = spawn(config.command, config.args, {
        env: childEnv,
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true,
      })

      let stdout = ''
      let stderr = ''
      let settled = false

      const finish = (result) => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        try {
          child.stdin.end()
        } catch {
          // ignore
        }
        if (!child.killed) {
          try {
            child.kill()
          } catch {
            // ignore
          }
        }
        resolve({
          ...result,
          durationMs: Date.now() - startedAt,
        })
      }

      const timer = setTimeout(() => {
        finish({
          ok: false,
          message: 'MCP server did not respond before the health-check timeout.',
          stderr: stderr.slice(-2000),
        })
      }, 6000)

      child.stdout.on('data', (chunk) => {
        stdout += chunk.toString('utf8')
        const lines = stdout.split(/\r?\n/).filter(Boolean)
        const toolsLine = lines.find((line) => {
          try {
            const parsed = JSON.parse(line)
            return parsed?.id === 2 && Array.isArray(parsed?.result?.tools)
          } catch {
            return false
          }
        })
        if (!toolsLine) return
        try {
          const parsed = JSON.parse(toolsLine)
          const toolNames = parsed.result.tools.map((tool) => tool.name).filter(Boolean)
          finish({
            ok: toolNames.includes('get_strategy_context') && toolNames.includes('get_cached_chronicle'),
            message: `MCP server responded with ${toolNames.length} tools.`,
            toolCount: toolNames.length,
            toolNames,
          })
        } catch (error) {
          finish({
            ok: false,
            message: error instanceof Error ? error.message : String(error),
          })
        }
      })

      child.stderr.on('data', (chunk) => {
        stderr += chunk.toString('utf8')
      })

      child.on('error', (error) => {
        finish({
          ok: false,
          message: error instanceof Error ? error.message : String(error),
          stderr: stderr.slice(-2000),
        })
      })

      child.on('exit', (code) => {
        if (settled) return
        finish({
          ok: false,
          message: `MCP server exited before completing health check (code ${code}).`,
          stderr: stderr.slice(-2000),
        })
      })

      const initialize = {
        jsonrpc: '2.0',
        id: 1,
        method: 'initialize',
        params: {
          protocolVersion: '2025-11-25',
          capabilities: {},
          clientInfo: {
            name: 'stellaris-companion-mcp-relay-health-check',
            version: app.getVersion(),
          },
        },
      }
      const toolsList = {
        jsonrpc: '2.0',
        id: 2,
        method: 'tools/list',
        params: {},
      }
      child.stdin.write(`${JSON.stringify(initialize)}\n`)
      child.stdin.write(`${JSON.stringify(toolsList)}\n`)
    })
  }

  return {
    getStatus,
    runHealthCheck,
    installClaudeDesktopConfig,
  }
}

module.exports = {
  createMcpRelayService,
}
