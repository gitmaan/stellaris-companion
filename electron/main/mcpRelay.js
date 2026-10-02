const fs = require('fs')
const os = require('os')
const path = require('path')
const { spawn, spawnSync } = require('child_process')

const SERVER_NAME = 'stellaris-companion'
const LEGACY_SERVER_NAMES = [SERVER_NAME, 'stellaris_companion', 'stellaris-companion-dev']
// 2026-07-28 is handshake-free; initialize-based compatibility probes use the
// latest handshake protocol while the SDK also serves modern request envelopes.
const PROTOCOL_VERSION = '2025-11-25'
const REQUIRED_TOOLS = ['get_active_campaign', 'get_strategy_context', 'get_cached_chronicle']
const MCPB_SETTINGS_MATCH = /^local\.mcpb\..*stellaris-companion.*mcp-relay.*\.json$/

function shellQuote(value) {
  const text = String(value)
  if (/^[A-Za-z0-9_/:=.,@%+-]+$/.test(text)) return text
  return `'${text.replace(/'/g, `'\\''`)}'`
}

function jsonPretty(value) {
  return JSON.stringify(value, null, 2)
}

function getClaudeDesktopConfigPath(home = os.homedir()) {
  if (process.platform === 'darwin') {
    return path.join(home, 'Library', 'Application Support', 'Claude', 'claude_desktop_config.json')
  }
  if (process.platform === 'win32') {
    const appData = (home === os.homedir() && process.env.APPDATA) || path.join(home, 'AppData', 'Roaming')
    return path.join(appData, 'Claude', 'claude_desktop_config.json')
  }
  return path.join(home, '.config', 'Claude', 'claude_desktop_config.json')
}

function getClaudeMcpbSettingsDir(home = os.homedir()) {
  if (process.platform === 'darwin') {
    return path.join(home, 'Library', 'Application Support', 'Claude', 'Claude Extensions Settings')
  }
  if (process.platform === 'win32') {
    const appData = (home === os.homedir() && process.env.APPDATA) || path.join(home, 'AppData', 'Roaming')
    return path.join(appData, 'Claude', 'Claude Extensions Settings')
  }
  return path.join(home, '.config', 'Claude', 'Claude Extensions Settings')
}

function getCursorConfigPath(home = os.homedir()) {
  return path.join(home, '.cursor', 'mcp.json')
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
    if (value !== undefined && value !== null && String(value) !== '') normalized[key] = String(value)
  })
  return normalized
}

function findExecutable(command, extraCandidates = []) {
  const candidates = [command, ...extraCandidates].filter(Boolean)
  const pathEnv = process.env.PATH || ''
  const extensions = process.platform === 'win32'
    ? (process.env.PATHEXT || '.EXE;.CMD;.BAT').split(';')
    : ['']
  for (const value of candidates) {
    if (path.isAbsolute(value) || value.includes(path.sep)) {
      if (fs.existsSync(value)) return value
      continue
    }
    for (const directory of pathEnv.split(path.delimiter)) {
      if (!directory) continue
      for (const extension of extensions) {
        const candidate = path.join(directory, `${value}${extension}`)
        if (fs.existsSync(candidate)) return candidate
      }
    }
  }
  return null
}

function resolveExecutable(command) {
  return findExecutable(command) || command
}

function sameArray(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false
  return a.every((value, index) => value === b[index])
}

function sameObject(a, b) {
  const left = normalizeConfigEnv(a)
  const right = normalizeConfigEnv(b)
  const keys = Object.keys(left).sort()
  return sameArray(keys, Object.keys(right).sort()) && keys.every(key => left[key] === right[key])
}

function serverLooksCurrent(server, target) {
  if (!server || typeof server !== 'object') return false
  return server.command === target.command &&
    sameArray(server.args || [], target.args || []) &&
    sameObject(server.env || {}, target.env || {})
}

function samePath(left, right) {
  if (!left || !right) return false
  return path.resolve(String(left)) === path.resolve(String(right))
}

function timestampForFile() {
  return new Date().toISOString().replace(/[:.]/g, '-')
}

function writeJsonAtomic(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
  const tempPath = `${filePath}.tmp-${process.pid}-${Date.now()}`
  const backupPath = fs.existsSync(filePath) ? `${filePath}.backup-${timestampForFile()}` : null
  fs.writeFileSync(tempPath, `${jsonPretty(value)}\n`, { encoding: 'utf8', mode: 0o600 })
  if (backupPath) {
    fs.copyFileSync(filePath, backupPath)
    try { fs.chmodSync(backupPath, 0o600) } catch { /* Windows may ignore POSIX modes */ }
  }
  try {
    fs.renameSync(tempPath, filePath)
  } catch (error) {
    try {
      fs.copyFileSync(tempPath, filePath)
      fs.unlinkSync(tempPath)
    } catch {
      try { fs.unlinkSync(tempPath) } catch { /* ignore cleanup */ }
      throw error
    }
  }
  try { fs.chmodSync(filePath, 0o600) } catch { /* Windows may ignore POSIX modes */ }
  return backupPath
}

function readMcpJsonConfig(configPath) {
  const existing = readJsonFile(configPath) || {}
  if (!existing || typeof existing !== 'object' || Array.isArray(existing)) {
    throw new Error('MCP config must be a JSON object.')
  }
  if (existing.mcpServers !== undefined &&
      (!existing.mcpServers || typeof existing.mcpServers !== 'object' || Array.isArray(existing.mcpServers))) {
    throw new Error('MCP config mcpServers must be a JSON object.')
  }
  return existing
}

function updateJsonClientConfig(configPath, serverConfig) {
  const existing = readMcpJsonConfig(configPath)
  const servers = { ...(existing.mcpServers || {}) }
  const hadStellarisServer = LEGACY_SERVER_NAMES.some(name => Object.hasOwn(servers, name))
  if (!serverConfig && !hadStellarisServer) {
    return { configPath, backupPath: null, changed: false }
  }
  LEGACY_SERVER_NAMES.forEach(name => { delete servers[name] })
  if (serverConfig) servers[SERVER_NAME] = serverConfig
  const updated = { ...existing, mcpServers: servers }
  if (JSON.stringify(existing) === JSON.stringify(updated)) {
    return { configPath, backupPath: null, changed: false }
  }
  const backupPath = writeJsonAtomic(configPath, updated)
  return { configPath, backupPath, changed: true }
}

function buildCodexCommand(config) {
  const envArgs = Object.entries(config.env || {})
    .map(([key, value]) => `--env ${shellQuote(`${key}=${value}`)}`)
    .join(' ')
  const command = [config.command, ...(config.args || [])].map(shellQuote).join(' ')
  return ['codex mcp add', SERVER_NAME, envArgs, '--', command].filter(Boolean).join(' ')
}

function buildCodexAddArgs(config) {
  const args = ['mcp', 'add', SERVER_NAME]
  Object.entries(config.env || {}).forEach(([key, value]) => args.push('--env', `${key}=${value}`))
  args.push('--', config.command, ...(config.args || []))
  return args
}

function buildClaudeCodeCommand(config) {
  const typedConfig = { type: 'stdio', command: config.command, args: config.args || [], env: config.env || {} }
  return `claude mcp add-json --scope user ${SERVER_NAME} ${shellQuote(JSON.stringify(typedConfig))}`
}

function createMcpRelayService({
  app,
  getPythonPath,
  getResolvedLanguage,
  homeDir = os.homedir(),
  codexExecutable: codexExecutableOverride,
  codexRunner: codexRunnerOverride,
}) {
  if (!app) throw new Error('createMcpRelayService: app is required')
  if (typeof getPythonPath !== 'function') throw new Error('createMcpRelayService: getPythonPath is required')
  if (typeof getResolvedLanguage !== 'function') throw new Error('createMcpRelayService: getResolvedLanguage is required')

  function getRepoRoot() {
    return path.resolve(__dirname, '..', '..')
  }

  function getCurrentAppPath() {
    if (!app.isPackaged) return getRepoRoot()
    if (process.platform === 'darwin') return path.resolve(path.dirname(process.execPath), '..', '..')
    return path.dirname(process.execPath)
  }

  function getBundledMcpbPath() {
    const base = app.isPackaged
      ? path.join(process.resourcesPath, 'mcpb')
      : path.join(getRepoRoot(), 'electron', 'generated', 'mcpb')
    const stable = path.join(base, 'stellaris-companion-mcp-relay.mcpb')
    return fs.existsSync(stable) ? stable : null
  }

  function buildLaunchConfig() {
    const userDataDir = app.getPath('userData')
    const dbPath = path.join(userDataDir, 'stellaris_history.db')
    const settingsPath = path.join(userDataDir, 'settings.json')
    const logDir = path.join(userDataDir, 'logs')
    const language = getResolvedLanguage()
    const command = resolveExecutable(getPythonPath())
    const args = app.isPackaged
      ? ['--mcp', '--db-path', dbPath, '--settings-path', settingsPath]
      : ['-m', 'backend.electron_main', '--mcp', '--db-path', dbPath, '--settings-path', settingsPath]
    const env = normalizeConfigEnv({
      STELLARIS_DB_PATH: dbPath,
      STELLARIS_LOG_DIR: logDir,
      STELLARIS_LOG_FILE_NAME: 'stellaris-companion-mcp.log',
      PYTHONPATH: app.isPackaged ? undefined : getRepoRoot(),
    })
    const serverConfig = { command, args, env }
    return {
      serverName: SERVER_NAME,
      dbPath,
      settingsPath,
      databaseExists: fs.existsSync(dbPath),
      logDir,
      logPath: path.join(logDir, 'stellaris-companion-mcp.log'),
      language,
      command,
      args,
      env,
      serverConfig,
      mcpbPath: getBundledMcpbPath(),
    }
  }

  function buildSnippets(config) {
    const desktopConfig = { mcpServers: { [SERVER_NAME]: config.serverConfig } }
    return {
      claudeDesktop: jsonPretty(desktopConfig),
      claudeCode: buildClaudeCodeCommand(config.serverConfig),
      codex: buildCodexCommand(config.serverConfig),
      genericJson: jsonPretty(desktopConfig),
    }
  }

  function getClaudeMcpbStatus() {
    const settingsDir = getClaudeMcpbSettingsDir(homeDir)
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
      const names = fs.readdirSync(settingsDir).filter(name => MCPB_SETTINGS_MATCH.test(name))
      if (names.length === 0) return status
      status.configPath = path.join(settingsDir, names.sort().at(-1))
      const existing = readJsonFile(status.configPath) || {}
      const userConfig = existing.userConfig && typeof existing.userConfig === 'object' ? existing.userConfig : {}
      status.configured = true
      status.enabled = existing.isEnabled !== false
      status.appPath = typeof userConfig.stellaris_companion_path === 'string'
        ? userConfig.stellaris_companion_path
        : null
      status.current = status.enabled && (!status.appPath || samePath(status.appPath, getCurrentAppPath()))
    } catch (error) {
      status.error = error instanceof Error ? error.message : String(error)
    }
    return status
  }

  function setClaudeMcpbEnabled(enabled) {
    const status = getClaudeMcpbStatus()
    if (status.error) return { error: status.error }
    if (!status.configured || !status.configPath) return null
    try {
      const existing = readJsonFile(status.configPath)
      if (!existing || typeof existing !== 'object' || Array.isArray(existing)) {
        return { error: 'Claude extension settings must be a JSON object.' }
      }
      if (existing.isEnabled === enabled) {
        return { configPath: status.configPath, backupPath: null, changed: false }
      }
      const backupPath = writeJsonAtomic(status.configPath, { ...existing, isEnabled: enabled })
      return { configPath: status.configPath, backupPath, changed: true }
    } catch (error) {
      return { error: error instanceof Error ? error.message : String(error) }
    }
  }

  function getJsonClientStatus(configPath, config) {
    const status = {
      configPath,
      configExists: fs.existsSync(configPath),
      configured: false,
      current: false,
      serverName: null,
      serverNames: [],
      error: null,
    }
    try {
      const existing = readJsonFile(configPath)
      const servers = existing?.mcpServers && typeof existing.mcpServers === 'object' ? existing.mcpServers : {}
      status.serverNames = LEGACY_SERVER_NAMES.filter(name => Object.hasOwn(servers, name))
      const selectedName = status.serverNames.includes(SERVER_NAME)
        ? SERVER_NAME
        : status.serverNames[0]
      if (!selectedName) return status
      status.configured = true
      status.serverName = selectedName
      status.current = status.serverNames.length === 1 &&
        selectedName === SERVER_NAME &&
        serverLooksCurrent(servers[selectedName], config.serverConfig)
    } catch (error) {
      status.error = error instanceof Error ? error.message : String(error)
    }
    return status
  }

  function getClaudeDesktopStatus(config) {
    const desktop = getJsonClientStatus(getClaudeDesktopConfigPath(homeDir), config)
    const mcpb = getClaudeMcpbStatus()
    const mcpbConnected = Boolean(mcpb.configured && mcpb.enabled)
    const duplicateConnections = desktop.configured && mcpbConnected
    return {
      ...desktop,
      configured: desktop.configured || mcpbConnected,
      current: !duplicateConnections && Boolean(desktop.current || (mcpbConnected && mcpb.current)),
      serverName: desktop.serverName || (mcpbConnected ? 'stellaris-companion-mcp-relay' : null),
      error: desktop.error || mcpb.error,
      mcpb,
    }
  }

  function getCodexExecutable() {
    if (codexExecutableOverride !== undefined) return codexExecutableOverride
    const extras = process.platform === 'darwin'
      ? [
          '/Applications/ChatGPT.app/Contents/Resources/codex',
          '/Applications/Codex.app/Contents/Resources/codex',
          path.join(homeDir, 'Applications', 'ChatGPT.app', 'Contents', 'Resources', 'codex'),
          path.join(homeDir, 'Applications', 'Codex.app', 'Contents', 'Resources', 'codex'),
          path.join(homeDir, '.local', 'bin', 'codex'),
          path.join(homeDir, '.npm-global', 'bin', 'codex'),
          '/opt/homebrew/bin/codex',
          '/usr/local/bin/codex',
        ]
      : []
    return findExecutable(process.env.CODEX_CLI_PATH || 'codex', extras)
  }

  function runCodex(executable, args) {
    if (typeof codexRunnerOverride === 'function') {
      return codexRunnerOverride(executable, args, { cwd: homeDir })
    }
    const result = spawnSync(executable, args, {
      encoding: 'utf8',
      cwd: homeDir,
      timeout: 3000,
      windowsHide: true,
      maxBuffer: 2 * 1024 * 1024,
    })
    return {
      ok: !result.error && result.status === 0,
      stdout: result.stdout || '',
      error: result.error?.message || (result.status === 0 ? null : (result.stderr || `Exit ${result.status}`).trim()),
    }
  }

  function getCodexStatus(config) {
    const executable = getCodexExecutable()
    const status = {
      executable,
      available: Boolean(executable),
      configured: false,
      current: false,
      serverName: null,
      serverNames: [],
      error: null,
    }
    if (!executable) return status
    const result = runCodex(executable, ['mcp', 'list', '--json'])
    if (!result.ok) {
      status.error = result.error
      return status
    }
    try {
      const entries = JSON.parse(result.stdout)
      const matches = Array.isArray(entries)
        ? entries.filter(item => LEGACY_SERVER_NAMES.includes(item?.name))
        : []
      status.serverNames = matches.map(item => item.name)
      const entry = matches.find(item => item.name === SERVER_NAME) || matches[0]
      if (!entry) return status
      status.configured = true
      status.serverName = entry.name
      const transport = entry.transport?.type === 'stdio' ? entry.transport : null
      status.current = Boolean(
        matches.length === 1 &&
        entry.name === SERVER_NAME &&
        entry.enabled !== false &&
        transport &&
        serverLooksCurrent({
          command: transport.command,
          args: transport.args || [],
          env: transport.env || {},
        }, config.serverConfig),
      )
    } catch (error) {
      status.error = error instanceof Error ? error.message : String(error)
    }
    return status
  }

  function getStatus() {
    const config = buildLaunchConfig()
    const claudeDesktop = getClaudeDesktopStatus(config)
    const codex = getCodexStatus(config)
    const cursor = getJsonClientStatus(getCursorConfigPath(homeDir), config)
    return {
      ...config,
      snippets: buildSnippets(config),
      claudeDesktop,
      codex,
      cursor,
      clients: { claude: claudeDesktop, codex, cursor },
    }
  }

  function installJsonClient(configPath, includeStatus = true) {
    const config = buildLaunchConfig()
    try {
      const result = updateJsonClientConfig(configPath, config.serverConfig)
      const response = { success: true, serverName: SERVER_NAME, ...result }
      if (includeStatus) response.status = getStatus()
      return response
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error), configPath }
    }
  }

  function disconnectJsonClient(configPath, includeStatus = true) {
    try {
      const result = updateJsonClientConfig(configPath, null)
      const response = { success: true, ...result }
      if (includeStatus) response.status = getStatus()
      return response
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error), configPath }
    }
  }

  function installClaudeDesktopConfig() {
    const result = installJsonClient(getClaudeDesktopConfigPath(homeDir), false)
    if (!result.success) return result
    const extensionResult = setClaudeMcpbEnabled(false)
    if (extensionResult?.error) {
      result.warning = `Connected Claude Desktop, but could not disable the older MCPB relay: ${extensionResult.error}`
    }
    result.status = getStatus()
    return result
  }

  function disconnectClaudeDesktopConfig() {
    const result = disconnectJsonClient(getClaudeDesktopConfigPath(homeDir), false)
    if (!result.success) return result
    const extensionResult = setClaudeMcpbEnabled(false)
    if (extensionResult?.error) {
      return { ...result, success: false, error: extensionResult.error, status: getStatus() }
    }
    result.status = getStatus()
    return result
  }

  function installCursorConfig() {
    return installJsonClient(getCursorConfigPath(homeDir))
  }

  function disconnectCursorConfig() {
    return disconnectJsonClient(getCursorConfigPath(homeDir))
  }

  function installCodexConfig() {
    const config = buildLaunchConfig()
    const executable = getCodexExecutable()
    if (!executable) {
      return { success: false, error: 'The Codex CLI used by ChatGPT desktop was not found.' }
    }
    const status = getCodexStatus(config)
    if (status.error) return { success: false, error: status.error }
    const added = runCodex(executable, buildCodexAddArgs(config.serverConfig))
    if (!added.ok) return { success: false, error: added.error }
    const result = { success: true, serverName: SERVER_NAME }
    for (const legacyName of status.serverNames.filter(name => name !== SERVER_NAME)) {
      const removed = runCodex(executable, ['mcp', 'remove', legacyName])
      if (!removed.ok) {
        result.warning = `Connected Codex, but could not remove the older ${legacyName} entry.`
        break
      }
    }
    result.status = getStatus()
    return result
  }

  function disconnectCodexConfig() {
    const config = buildLaunchConfig()
    const executable = getCodexExecutable()
    if (!executable) {
      return { success: false, error: 'The Codex CLI used by ChatGPT desktop was not found.' }
    }
    const status = getCodexStatus(config)
    if (status.error) return { success: false, error: status.error }
    for (const serverName of status.serverNames) {
      const removed = runCodex(executable, ['mcp', 'remove', serverName])
      if (!removed.ok) return { success: false, error: removed.error }
    }
    return { success: true, status: getStatus() }
  }

  function runHealthCheck() {
    const config = buildLaunchConfig()
    return new Promise((resolve) => {
      const startedAt = Date.now()
      const child = spawn(config.command, config.args, {
        env: { ...process.env, ...config.env },
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true,
      })
      let stdoutBuffer = ''
      let stderr = ''
      let settled = false
      let initializeResult = null
      let toolNames = []

      const send = payload => child.stdin.write(`${JSON.stringify(payload)}\n`)
      const finish = result => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        const shutdownTimer = setTimeout(() => {
          if (child.exitCode === null) {
            try { child.kill() } catch { /* ignore */ }
          }
        }, 500)
        shutdownTimer.unref?.()
        child.once('close', () => {
          clearTimeout(shutdownTimer)
          resolve({ ...result, durationMs: Date.now() - startedAt })
        })
        try { child.stdin.end() } catch { /* ignore */ }
      }
      const fail = message => finish({
        ok: false,
        serverHealthy: false,
        campaignReady: false,
        message,
        stderr: stderr.slice(-2000),
      })
      const timer = setTimeout(
        () => fail('MCP server did not respond before the health-check timeout.'),
        10000,
      )

      const handleMessage = message => {
        if (message?.id === 1) {
          if (message.error) return fail(message.error.message || 'MCP initialization failed.')
          initializeResult = message.result || {}
          send({ jsonrpc: '2.0', method: 'notifications/initialized', params: {} })
          send({ jsonrpc: '2.0', id: 2, method: 'tools/list', params: {} })
          return
        }
        if (message?.id === 2) {
          if (message.error) return fail(message.error.message || 'MCP tool discovery failed.')
          toolNames = Array.isArray(message?.result?.tools)
            ? message.result.tools.map(tool => tool.name).filter(Boolean)
            : []
          if (!REQUIRED_TOOLS.every(name => toolNames.includes(name))) {
            return fail('MCP server is missing required Stellaris Companion tools.')
          }
          send({
            jsonrpc: '2.0',
            id: 3,
            method: 'tools/call',
            params: { name: 'get_active_campaign', arguments: {} },
          })
          return
        }
        if (message?.id === 3) {
          if (message.error) return fail(message.error.message || 'Campaign readiness check failed.')
          const result = message.result || {}
          if (result.isError) return fail(result.content?.[0]?.text || 'Campaign readiness check failed.')
          const campaign = result.structuredContent || {}
          const campaignReady = campaign.save_loaded === true
          finish({
            ok: true,
            serverHealthy: true,
            campaignReady,
            campaign,
            message: campaignReady
              ? `Ready for ${campaign.empire_name || 'the active campaign'} on ${campaign.game_date || 'the latest date'}.`
              : 'MCP is connected, but no campaign is cached yet. Load a Stellaris save in the app first.',
            toolCount: toolNames.length,
            toolNames,
            protocolVersion: initializeResult?.protocolVersion || null,
            serverVersion: initializeResult?.serverInfo?.version || null,
          })
        }
      }

      child.stdout.on('data', chunk => {
        stdoutBuffer += chunk.toString('utf8')
        const lines = stdoutBuffer.split(/\r?\n/)
        stdoutBuffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.trim()) continue
          try { handleMessage(JSON.parse(line)) } catch { /* Ignore non-protocol stdout noise. */ }
        }
      })
      child.stderr.on('data', chunk => {
        stderr = (stderr + chunk.toString('utf8')).slice(-8000)
      })
      child.stdin.on('error', error => fail(error.message))
      child.on('error', error => fail(error.message))
      child.on('exit', code => {
        if (!settled) fail(`MCP server exited before completing the health check (code ${code}).`)
      })

      send({
        jsonrpc: '2.0',
        id: 1,
        method: 'initialize',
        params: {
          protocolVersion: PROTOCOL_VERSION,
          capabilities: {},
          clientInfo: {
            name: 'stellaris-companion-health-check',
            version: app.getVersion(),
          },
        },
      })
    })
  }

  return {
    getStatus,
    runHealthCheck,
    installClaudeDesktopConfig,
    disconnectClaudeDesktopConfig,
    installCodexConfig,
    disconnectCodexConfig,
    installCursorConfig,
    disconnectCursorConfig,
    getBundledMcpbPath,
  }
}

module.exports = {
  SERVER_NAME,
  buildCodexAddArgs,
  createMcpRelayService,
  serverLooksCurrent,
  updateJsonClientConfig,
  writeJsonAtomic,
}
