// Run scripts/check_advisor_answers.py against the ChatGPT plan connected in the app.
//
//   electron/node_modules/.bin/electron scripts/advisor_check_chatgpt.cjs [check options]
//
// The backend never holds a ChatGPT credential: the desktop app gives it a local
// bridge and a one-time capability for it. This starts the same bridge from the
// app's saved profile, inside Electron, and hands the check the same two values.
// No credential is exported, copied or printed. Quit the app first, so two
// processes do not refresh the same sign-in. Every question spends plan usage.
const path = require('node:path')
const { spawn } = require('node:child_process')
const { createRequire } = require('node:module')

const root = path.resolve(__dirname, '..')
const fromElectron = createRequire(path.join(root, 'electron/package.json'))
const { app, safeStorage } = fromElectron('electron')
const Store = fromElectron('electron-store')
const { createSecretStorage } = require('../electron/main/secureStorage')
const { createChatGPTService } = require('../electron/main/chatgpt')
const { createChatGPTBridge } = require('../electron/main/chatgptBridge')

app.setName('stellaris-companion')

async function main() {
  await app.whenReady()
  const store = new Store({ name: 'settings', cwd: app.getPath('userData') })
  const secrets = createSecretStorage({ safeStorage, store })
  const service = createChatGPTService({
    store, getSecret: secrets.getSecret, setSecret: secrets.setSecret,
    openExternal: () => { throw new Error('Sign in from the app, then run this again') },
  })
  const status = service.status()
  if (!status.ready) throw new Error('Connect ChatGPT in Stellaris Companion first')
  const bridge = createChatGPTBridge(service)
  await bridge.start()
  const { url, token } = bridge.connection()
  const marker = process.argv.indexOf('--')
  const options = marker >= 0 ? process.argv.slice(marker + 1) : process.argv.slice(2)
  const child = spawn(process.env.PYTHON || 'python3',
    [path.join(root, 'scripts/check_advisor_answers.py'), '--provider', 'chatgpt', ...options], {
      cwd: root, stdio: 'inherit',
      env: { ...process.env, PYTHONPATH: root, STELLARIS_ADVISOR_PROVIDER: 'chatgpt',
        STELLARIS_ADVISOR_MODEL: status.model, STELLARIS_CHATGPT_BRIDGE_URL: url,
        STELLARIS_CHATGPT_BRIDGE_TOKEN: token },
    })
  const code = await new Promise(resolve => { child.on('exit', resolve); child.on('error', () => resolve(1)) })
  bridge.close()
  app.exit(code ?? 1)
}

main().catch(error => { console.error(error.message); app.exit(1) })
