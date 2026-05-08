#!/usr/bin/env node

const fs = require('fs')
const os = require('os')
const path = require('path')
const { spawn } = require('child_process')

const APP_NAME = 'Stellaris Companion'
const PACKAGE_NAME = 'stellaris-companion'

function cleanConfigValue(value) {
  if (!value || typeof value !== 'string') return ''
  if (value.includes('${user_config.')) return ''
  return value.trim()
}

function pathExists(candidate) {
  try {
    return !!candidate && fs.existsSync(candidate)
  } catch {
    return false
  }
}

function isExecutable(candidate) {
  try {
    fs.accessSync(candidate, fs.constants.X_OK)
    return true
  } catch {
    return pathExists(candidate)
  }
}

function defaultUserDataDir() {
  const configured = cleanConfigValue(process.env.STELLARIS_COMPANION_USER_DATA_DIR)
  if (configured) return configured

  const home = os.homedir()
  if (process.platform === 'darwin') {
    return path.join(home, 'Library', 'Application Support', PACKAGE_NAME)
  }
  if (process.platform === 'win32') {
    const appData = process.env.APPDATA || path.join(home, 'AppData', 'Roaming')
    return path.join(appData, PACKAGE_NAME)
  }
  return path.join(home, '.config', PACKAGE_NAME)
}

function sourceCheckoutLaunchFromPath(appPath) {
  const sourceEntry = path.join(appPath, 'backend', 'electron_main.py')
  if (!pathExists(sourceEntry)) return null

  const pythonCandidates = process.platform === 'win32'
    ? [
        path.join(appPath, '.venv', 'Scripts', 'python.exe'),
        path.join(appPath, 'venv', 'Scripts', 'python.exe'),
        'python',
      ]
    : [
        path.join(appPath, '.venv', 'bin', 'python3'),
        path.join(appPath, 'venv', 'bin', 'python3'),
        'python3',
      ]

  const pythonCommand = pythonCandidates.find((candidate) => {
    if (path.isAbsolute(candidate)) return isExecutable(candidate)
    return true
  })

  return {
    command: pythonCommand,
    baseArgs: ['-m', 'backend.electron_main'],
    env: {
      PYTHONPATH: [
        appPath,
        process.env.PYTHONPATH,
      ].filter(Boolean).join(path.delimiter),
    },
  }
}

function backendLaunchFromAppPath(appPath) {
  if (!appPath) return null

  const sourceLaunch = sourceCheckoutLaunchFromPath(appPath)
  if (sourceLaunch) return sourceLaunch

  const candidates = []
  if (process.platform === 'darwin') {
    candidates.push(path.join(appPath, 'Contents', 'Resources', 'python-backend', 'stellaris-backend'))
    candidates.push(path.join(appPath, 'Resources', 'python-backend', 'stellaris-backend'))
    candidates.push(path.join(appPath, 'dist-python', 'stellaris-backend', 'stellaris-backend'))
    candidates.push(path.join(appPath, 'build', 'stellaris-backend', 'stellaris-backend'))
  } else if (process.platform === 'win32') {
    candidates.push(path.join(appPath, 'resources', 'python-backend', 'stellaris-backend.exe'))
    candidates.push(path.join(appPath, 'python-backend', 'stellaris-backend.exe'))
    candidates.push(path.join(appPath, 'dist-python', 'stellaris-backend', 'stellaris-backend.exe'))
    candidates.push(path.join(appPath, 'build', 'stellaris-backend', 'stellaris-backend.exe'))
  }

  const backendPath = candidates.find(isExecutable)
  if (backendPath) {
    return {
      command: backendPath,
      baseArgs: [],
    }
  }

  if (isExecutable(appPath)) {
    return {
      command: appPath,
      baseArgs: [],
    }
  }

  return null
}

function defaultAppPathCandidates() {
  const home = os.homedir()
  if (process.platform === 'darwin') {
    return [
      path.join('/Applications', `${APP_NAME}.app`),
      path.join(home, 'Applications', `${APP_NAME}.app`),
    ]
  }
  if (process.platform === 'win32') {
    const localAppData = process.env.LOCALAPPDATA || path.join(home, 'AppData', 'Local')
    return [
      path.join(localAppData, 'Programs', PACKAGE_NAME),
      path.join(localAppData, 'Programs', APP_NAME),
      path.join(process.env.ProgramFiles || 'C:\\Program Files', APP_NAME),
      path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', APP_NAME),
    ]
  }
  return []
}

function splitCommandArgs(raw) {
  const cleaned = cleanConfigValue(raw)
  if (!cleaned) return []
  try {
    const parsed = JSON.parse(cleaned)
    if (Array.isArray(parsed)) return parsed.map(String)
  } catch {
    // Fall through to simple whitespace splitting for local development.
  }
  return cleaned.split(/\s+/).filter(Boolean)
}

function resolveBackendLaunch() {
  const commandOverride = cleanConfigValue(process.env.STELLARIS_COMPANION_BACKEND_COMMAND)
  if (commandOverride) {
    return {
      command: commandOverride,
      baseArgs: splitCommandArgs(process.env.STELLARIS_COMPANION_BACKEND_ARGS),
    }
  }

  const backendPathOverride = cleanConfigValue(process.env.STELLARIS_COMPANION_BACKEND_PATH)
  if (backendPathOverride) {
    return {
      command: backendPathOverride,
      baseArgs: [],
    }
  }

  const configuredAppPath = cleanConfigValue(process.env.STELLARIS_COMPANION_APP_PATH)
  const appCandidates = [
    configuredAppPath,
    ...defaultAppPathCandidates(),
  ].filter(Boolean)

  for (const appPath of appCandidates) {
    const launch = backendLaunchFromAppPath(appPath)
    if (launch) return launch
  }

  return null
}

function buildArgs(baseArgs) {
  const dbPath = cleanConfigValue(process.env.STELLARIS_COMPANION_DB_PATH) ||
    path.join(defaultUserDataDir(), 'stellaris_history.db')
  const language = cleanConfigValue(process.env.STELLARIS_COMPANION_LANGUAGE) || 'en'
  return [
    ...baseArgs,
    '--mcp',
    '--db-path',
    dbPath,
    '--language',
    language,
  ]
}

function main() {
  const launch = resolveBackendLaunch()
  if (!launch) {
    console.error(
      [
        'Stellaris Companion MCP Relay could not find the Stellaris Companion backend.',
        'Install Stellaris Companion, or configure the extension with the app location.',
      ].join(' '),
    )
    process.exit(1)
  }

  const child = spawn(launch.command, buildArgs(launch.baseArgs), {
    env: {
      ...process.env,
      ...(launch.env || {}),
    },
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  })

  let stdoutBuffer = ''
  const stdoutQueue = []
  let stdoutFlushScheduled = false

  const flushStdoutQueue = () => {
    const line = stdoutQueue.shift()
    if (line !== undefined) {
      process.stdout.write(`${line}\n`)
      setTimeout(flushStdoutQueue, 5)
      return
    }
    stdoutFlushScheduled = false
  }

  const enqueueStdoutLine = (line) => {
    if (!line) return
    stdoutQueue.push(line)
    if (!stdoutFlushScheduled) {
      stdoutFlushScheduled = true
      setImmediate(flushStdoutQueue)
    }
  }

  process.stdin.pipe(child.stdin)
  child.stdout.on('data', (chunk) => {
    stdoutBuffer += chunk.toString('utf8')
    const lines = stdoutBuffer.split(/\r?\n/)
    stdoutBuffer = lines.pop() || ''
    lines.forEach(enqueueStdoutLine)
  })
  child.stderr.pipe(process.stderr)

  child.on('error', (error) => {
    console.error(`Failed to start Stellaris Companion MCP backend: ${error.message}`)
    process.exit(1)
  })

  child.on('exit', (code, signal) => {
    const remainingStdout = stdoutBuffer.trim()
    if (remainingStdout) process.stdout.write(`${remainingStdout}\n`)
    if (signal) {
      process.kill(process.pid, signal)
      return
    }
    process.exit(code || 0)
  })

  const shutdown = () => {
    if (!child.killed) child.kill()
  }
  process.on('SIGINT', shutdown)
  process.on('SIGTERM', shutdown)
}

main()
