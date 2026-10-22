const path = require('node:path')
const assert = require('node:assert/strict')

function getElectronLaunchArgs(entrypoint) {
  const args = []
  if (process.env.E2E_NO_SANDBOX === '1') args.push('--no-sandbox')
  args.push(entrypoint)
  return args
}

// Only opt-in journeys use the installed binary; the normal suite keeps its source launch.
function getElectronLaunchOptions(entrypoint, extraArgs = []) {
  if (!process.env.E2E_EXECUTABLE_PATH) {
    return { args: [...extraArgs, ...getElectronLaunchArgs(entrypoint)] }
  }
  return {
    executablePath: path.resolve(process.env.E2E_EXECUTABLE_PATH),
    args: [...extraArgs, ...(process.env.E2E_NO_SANDBOX === '1' ? ['--no-sandbox'] : [])],
  }
}

async function assertPackagedApp(electronApp) {
  if (!process.env.E2E_EXECUTABLE_PATH) return
  const runtime = await electronApp.evaluate(({ app }) => ({
    packaged: app.isPackaged, executable: process.execPath,
    version: app.getVersion(), appPath: app.getAppPath(),
  }))
  assert.equal(runtime.packaged, true, 'The gate must run the packaged application')
  assert.equal(path.normalize(runtime.executable).toLowerCase(),
    path.resolve(process.env.E2E_EXECUTABLE_PATH).toLowerCase())
  assert.equal(runtime.version, require('../../package.json').version)
  assert.match(runtime.appPath, /app\.asar$/)
}

module.exports = { getElectronLaunchArgs, getElectronLaunchOptions, assertPackagedApp }
