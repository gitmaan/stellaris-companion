const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const {
  buildCodexAddArgs,
  createMcpRelayService,
  serverLooksCurrent,
  updateJsonClientConfig,
} = require('../main/mcpRelay')

test('JSON client config updates are scoped, backed up, and remove legacy names', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'stellaris-mcp-config-'))
  const configPath = path.join(tempDir, 'mcp.json')
  fs.writeFileSync(configPath, JSON.stringify({
    theme: 'dark',
    mcpServers: {
      keep: { command: 'keep-me' },
      stellaris_companion: { command: 'old-command' },
    },
  }))
  const target = {
    command: '/app/backend',
    args: ['--mcp'],
    env: { STELLARIS_DB_PATH: '/data/history.db' },
  }

  const result = updateJsonClientConfig(configPath, target)
  const updated = JSON.parse(fs.readFileSync(configPath, 'utf8'))

  assert.equal(updated.theme, 'dark')
  assert.deepEqual(updated.mcpServers.keep, { command: 'keep-me' })
  assert.equal(updated.mcpServers.stellaris_companion, undefined)
  assert.deepEqual(updated.mcpServers['stellaris-companion'], target)
  assert.ok(result.backupPath)
  assert.ok(fs.existsSync(result.backupPath))
})

test('current config comparison includes command, arguments, and environment', () => {
  const target = { command: '/app/backend', args: ['--mcp'], env: { A: '1' } }
  assert.equal(serverLooksCurrent({ ...target }, target), true)
  assert.equal(serverLooksCurrent({ ...target, env: { A: '2' } }, target), false)
})

test('Codex setup uses structured argv without shell interpolation', () => {
  const args = buildCodexAddArgs({
    command: '/Applications/Stellaris Companion/backend',
    args: ['--mcp', '--db-path', '/tmp/path with spaces/history.db'],
    env: { STELLARIS_LOG_DIR: '/tmp/log path' },
  })
  assert.deepEqual(args, [
    'mcp',
    'add',
    'stellaris-companion',
    '--env',
    'STELLARIS_LOG_DIR=/tmp/log path',
    '--',
    '/Applications/Stellaris Companion/backend',
    '--mcp',
    '--db-path',
    '/tmp/path with spaces/history.db',
  ])
})

test('Claude disconnect also disables a legacy MCPB relay', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'stellaris-mcp-claude-'))
  const homeDir = path.join(tempDir, 'home')
  const settingsDir = process.platform === 'darwin'
    ? path.join(homeDir, 'Library', 'Application Support', 'Claude', 'Claude Extensions Settings')
    : process.platform === 'win32'
      ? path.join(homeDir, 'AppData', 'Roaming', 'Claude', 'Claude Extensions Settings')
      : path.join(homeDir, '.config', 'Claude', 'Claude Extensions Settings')
  fs.mkdirSync(settingsDir, { recursive: true })
  const extensionPath = path.join(
    settingsDir,
    'local.mcpb.test-stellaris-companion-mcp-relay.1.json',
  )
  const repoRoot = path.resolve(__dirname, '..', '..')
  fs.writeFileSync(extensionPath, JSON.stringify({
    isEnabled: true,
    userConfig: { stellaris_companion_path: repoRoot },
  }))

  const service = createMcpRelayService({
    app: {
      isPackaged: false,
      getPath: () => tempDir,
      getVersion: () => 'test',
    },
    getPythonPath: () => '/app/backend',
    getResolvedLanguage: () => 'en',
    homeDir,
    codexExecutable: null,
  })

  assert.equal(service.getStatus().clients.claude.current, true)
  const disconnected = service.disconnectClaudeDesktopConfig()
  assert.equal(disconnected.success, true)
  assert.equal(JSON.parse(fs.readFileSync(extensionPath, 'utf8')).isEnabled, false)
  assert.equal(disconnected.status.clients.claude.configured, false)
  assert.ok(fs.readdirSync(settingsDir).some(name => name.includes('.backup-')))

  const connected = service.installClaudeDesktopConfig()
  assert.equal(connected.success, true)
  assert.equal(connected.status.clients.claude.current, true)
  assert.equal(JSON.parse(fs.readFileSync(extensionPath, 'utf8')).isEnabled, false)

  const duplicateSettings = JSON.parse(fs.readFileSync(extensionPath, 'utf8'))
  fs.writeFileSync(extensionPath, JSON.stringify({ ...duplicateSettings, isEnabled: true }))
  assert.equal(service.getStatus().clients.claude.current, false)
  const reconciled = service.installClaudeDesktopConfig()
  assert.equal(reconciled.status.clients.claude.current, true)
  assert.equal(JSON.parse(fs.readFileSync(extensionPath, 'utf8')).isEnabled, false)
})

test('Codex update installs the current entry before removing every legacy entry', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'stellaris-mcp-codex-'))
  const calls = []
  let updated = false
  const currentEntry = {
    name: 'stellaris-companion',
    enabled: true,
    transport: {
      type: 'stdio',
      command: '/app/backend',
      args: [
        '-m',
        'backend.electron_main',
        '--mcp',
        '--db-path',
        path.join(tempDir, 'stellaris_history.db'),
        '--settings-path',
        path.join(tempDir, 'settings.json'),
      ],
      env: {
        STELLARIS_DB_PATH: path.join(tempDir, 'stellaris_history.db'),
        STELLARIS_LOG_DIR: path.join(tempDir, 'logs'),
        STELLARIS_LOG_FILE_NAME: 'stellaris-companion-mcp.log',
        PYTHONPATH: path.resolve(__dirname, '..', '..'),
      },
    },
  }
  const legacyEntries = [
    currentEntry,
    {
      name: 'stellaris_companion',
      enabled: true,
      transport: { type: 'stdio', command: '/old-one', args: [], env: {} },
    },
    {
      name: 'stellaris-companion-dev',
      enabled: true,
      transport: { type: 'stdio', command: '/old-two', args: [], env: {} },
    },
  ]
  const service = createMcpRelayService({
    app: {
      isPackaged: false,
      getPath: () => tempDir,
      getVersion: () => 'test',
    },
    getPythonPath: () => '/app/backend',
    getResolvedLanguage: () => 'en',
    homeDir: tempDir,
    codexExecutable: '/fake/codex',
    codexRunner: (_executable, args) => {
      calls.push(args)
      if (args[1] === 'list') {
        const current = updated ? [currentEntry] : legacyEntries
        return { ok: true, stdout: JSON.stringify(current), error: null }
      }
      if (args[1] === 'add') updated = true
      return { ok: true, stdout: '', error: null }
    },
  })

  assert.equal(service.getStatus().clients.codex.current, false)
  const result = service.installCodexConfig()

  assert.equal(result.success, true)
  const mutationCalls = calls.filter(args => args[1] !== 'list')
  assert.equal(mutationCalls[0][1], 'add')
  assert.deepEqual(
    mutationCalls.slice(1).map(args => args.slice(0, 4)),
    [
      ['mcp', 'remove', 'stellaris_companion'],
      ['mcp', 'remove', 'stellaris-companion-dev'],
    ],
  )
})

test('health check completes initialization and distinguishes an empty campaign', async t => {
  const repoRoot = path.resolve(__dirname, '..', '..')
  const venvPython = path.join(repoRoot, '.venv', process.platform === 'win32' ? 'Scripts' : 'bin', process.platform === 'win32' ? 'python.exe' : 'python')
  const python = process.env.PYTHON_BIN || (fs.existsSync(venvPython) ? venvPython : process.platform === 'win32' ? 'python' : 'python3')
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'stellaris-mcp-health-'))
  t.after(() => fs.rmSync(userDataDir, { recursive: true, force: true }))
  const service = createMcpRelayService({
    app: {
      isPackaged: false,
      getPath: () => userDataDir,
      getVersion: () => 'test',
    },
    getPythonPath: () => python,
    getResolvedLanguage: () => 'en',
    homeDir: path.join(userDataDir, 'home'),
  })

  const result = await service.runHealthCheck()

  assert.equal(result.ok, true)
  assert.equal(result.serverHealthy, true)
  assert.equal(result.campaignReady, false)
  assert.equal(result.toolCount, 10)
  assert.match(result.message, /no campaign is cached/i)
})
