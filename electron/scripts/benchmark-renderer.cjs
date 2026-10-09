/* Fresh-profile, hidden Electron measurements. Run against either checkout with
 * --app-root /path/to/repository and --output /path/to/result.json. No timing
 * thresholds: compare repeated runs on the same machine and report the noise. */
const fs = require('node:fs/promises')
const path = require('node:path')
const os = require('node:os')
const { createRequire } = require('node:module')
const { performance } = require('node:perf_hooks')
const { execFileSync } = require('node:child_process')

const argument = (name, fallback) => {
  const index = process.argv.indexOf(name)
  return index < 0 ? fallback : process.argv[index + 1]
}
const root = path.resolve(argument('--app-root', path.join(__dirname, '../..')))
const output = path.resolve(argument('--output', path.join(root, 'artifacts/frontend-performance/benchmark.json')))
const sampleCount = Number(argument('--samples', '5'))
if (!Number.isInteger(sampleCount) || sampleCount < 1) throw new Error('--samples must be a positive integer')
const requireApp = createRequire(path.join(root, 'electron/package.json'))
const { _electron: electron } = requireApp('@playwright/test')
const { createMockChronicleBackend } = requireApp('./e2e/helpers/mockBackend')
const { getElectronLaunchArgs } = requireApp('./e2e/helpers/electronLaunch')
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
const metricValues = result => Object.fromEntries(result.metrics.map(item => [item.name, item.value]))
const median = values => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)]

async function runSample(index) {
  const turns = Array.from({ length: 150 }, (_, i) => ({
    id: `turn-${i}`, request_id: `turn-${i}`, question: `Review expedition ${i}.`,
    answer: `## Expedition ${i}\n\n${'Check the **escort fleet**, shipyards, and supply routes before departure. '.repeat(8)}\n\n- Keep an alloy reserve.\n- Review [the official site](https://www.paradoxinteractive.com/).`,
    game_date: '2205.01.01', created_at: 1700000000 + i, language: 'en',
  }))
  const backend = createMockChronicleBackend({ conversations: [{ id: 'performance-chat', save_id: 'save-1', title: 'Expedition review', created_at: 1, updated_at: 2, turns }] })
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-renderer-perf-'))
  let app
  try {
    const start = performance.now()
    app = await electron.launch({
      // Resolve Playwright from the measured checkout, so its normal Electron
      // loader and that checkout's runtime are used together. executablePath
      // bypasses Playwright's loader and can race renderer attachment.
      timeout: 45_000,
      args: getElectronLaunchArgs(path.join(root, 'electron/main.js')),
      env: { ...process.env, NODE_ENV: 'test', E2E: '1', E2E_SHOW_WINDOWS: '0', E2E_ONBOARDING_COMPLETE: '1', E2E_BACKEND_CONFIGURED: '1', E2E_SKIP_BACKEND_AUTOSTART: '1', E2E_FAKE_SECURE_STORAGE: '1', E2E_USER_DATA_DIR: profile, STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'renderer-perf-fixture-token' },
    })
    const page = await app.firstWindow()
    page.setDefaultTimeout(20_000)
    await page.waitForSelector('#page-chat textarea')
    const shellReadyMs = performance.now() - start
    await page.waitForFunction(() => {
      const input = document.querySelector('#page-chat textarea')
      return input && !input.disabled && document.querySelector('[data-message-id="turn-149"]')
    })
    const launchToReadyMs = performance.now() - start
    const native = await app.evaluate(({ BrowserWindow }) => {
      const window = BrowserWindow.getAllWindows()[0]
      return { visible: window.isVisible(), focused: window.isFocused(), electron: process.versions.electron, chrome: process.versions.chrome }
    })
    if (native.visible || native.focused) throw new Error('Benchmark must remain hidden')
    if (native.electron !== requireApp('electron/package.json').version) throw new Error('Benchmark launched a different Electron version than the measured checkout')
    // file:// loads do not populate Chromium Resource Timing. The debugger
    // enumerates parsed scripts when enabled, including already-loaded modules.
    const scripts = new Set()
    const scriptSession = await app.context().newCDPSession(page)
    scriptSession.on('Debugger.scriptParsed', script => {
      if (script.url.startsWith('file:') && script.url.includes('/dist/assets/') && script.url.endsWith('.js')) scripts.add(path.basename(script.url))
    })
    await scriptSession.send('Debugger.enable')
    await scriptSession.send('Debugger.disable')
    await scriptSession.detach()
    const resources = [...scripts].sort()
    if (index !== 0) return { shellReadyMs, launchToReadyMs, native, resources }

    // Install instrumentation before a reload, so native ResizeObserver work can
    // be compared without adding any counters to the production renderer.
    await page.addInitScript(() => {
      const stats = window.__rendererPerf = { observersCreated: 0, observersDisconnected: 0, rowObservations: 0 }
      const NativeResizeObserver = window.ResizeObserver
      window.ResizeObserver = class extends NativeResizeObserver {
        constructor(callback) { super(callback); stats.observersCreated++ }
        observe(target, options) { if (target.matches('[data-message-id]')) stats.rowObservations++; return super.observe(target, options) }
        disconnect() { stats.observersDisconnected++; return super.disconnect() }
      }
    })
    await page.reload()
    await page.waitForSelector('[data-message-id="turn-149"]')
    await page.evaluate(() => document.fonts.ready)
    await delay(500)
    const cdp = await app.context().newCDPSession(page)
    await cdp.send('Performance.enable')
    const idleBefore = metricValues(await cdp.send('Performance.getMetrics'))
    await delay(3000)
    const idleAfter = metricValues(await cdp.send('Performance.getMetrics'))
    const idle = {
      durationMs: (idleAfter.Timestamp - idleBefore.Timestamp) * 1000,
      rendererTaskMs: (idleAfter.TaskDuration - idleBefore.TaskDuration) * 1000,
      jsHeapUsedBytes: idleAfter.JSHeapUsedSize,
      processMemory: await app.evaluate(({ app }) => app.getAppMetrics().filter(item => item.type === 'Tab').map(item => item.memory)),
      visibility: await page.evaluate(() => document.visibilityState),
    }
    const before = metricValues(await cdp.send('Performance.getMetrics'))
    const scrolling = await page.evaluate(async () => {
      const scroller = document.querySelector('[data-chat-scroll]')
      scroller.scrollTop = 2000
      await new Promise(resolve => setTimeout(resolve, 300))
      const start = { ...window.__rendererPerf }
      const frames = []
      let previous = performance.now()
      for (let i = 0; i < 180; i++) {
        await new Promise(resolve => requestAnimationFrame(resolve))
        const now = performance.now()
        frames.push(now - previous); previous = now
        scroller.scrollTop += 28
      }
      await new Promise(resolve => requestAnimationFrame(resolve))
      const ordered = [...frames].sort((a, b) => a - b)
      return {
        frameP50Ms: ordered[Math.floor(ordered.length / 2)], frameP95Ms: ordered[Math.floor(ordered.length * .95)], frameMaxMs: Math.max(...frames),
        observersCreated: window.__rendererPerf.observersCreated - start.observersCreated,
        observersDisconnected: window.__rendererPerf.observersDisconnected - start.observersDisconnected,
        rowObservations: window.__rendererPerf.rowObservations - start.rowObservations,
        mountedMessages: document.querySelectorAll('[data-message-id]').length,
      }
    })
    const after = metricValues(await cdp.send('Performance.getMetrics'))
    scrolling.rendererTaskMs = (after.TaskDuration - before.TaskDuration) * 1000
    scrolling.scriptMs = (after.ScriptDuration - before.ScriptDuration) * 1000
    scrolling.layoutMs = (after.LayoutDuration - before.LayoutDuration) * 1000
    const input = page.locator('#page-chat textarea')
    await input.focus()
    const typingBefore = metricValues(await cdp.send('Performance.getMetrics'))
    const typingStarted = performance.now()
    await input.pressSequentially('Compare our fleets and prepare the next expedition.', { delay: 5 })
    const typingAfter = metricValues(await cdp.send('Performance.getMetrics'))
    const typing = { durationMs: performance.now() - typingStarted, rendererTaskMs: (typingAfter.TaskDuration - typingBefore.TaskDuration) * 1000 }
    await cdp.detach()
    return { shellReadyMs, launchToReadyMs, native, resources, idle, scrolling, typing }
  } finally {
    if (app) await app.close()
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
}

async function main() {
  const samples = []
  for (let i = 0; i < sampleCount; i++) {
    samples.push(await runSample(i))
    process.stdout.write(`Sample ${i + 1}/${sampleCount}: ${samples[i].launchToReadyMs.toFixed(1)} ms launch to ready\n`)
  }
  const dist = path.join(root, 'electron/renderer/dist/assets')
  const assets = await fs.readdir(dist)
  const startupJsFiles = samples[0].resources
  const startupJsBytes = (await Promise.all(startupJsFiles.map(async name => (await fs.stat(path.join(dist, name))).size))).reduce((sum, size) => sum + size, 0)
  const report = {
    recordedAt: new Date().toISOString(), commit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
    workingTreeDirty: Boolean(execFileSync('git', ['status', '--porcelain'], { cwd: root, encoding: 'utf8' }).trim()),
    environment: { platform: process.platform, arch: process.arch, os: os.release(), cpu: os.cpus()[0].model },
    methodology: 'Fresh Electron profiles, warm OS file caches, local deterministic mock backend, hidden unthrottled windows; 150 saved turns (300 messages), 180 scroll frames, 3-second idle sample. Timings are diagnostic, not release gates or visible-window FPS claims.',
    shellReadyMedianMs: median(samples.map(item => item.shellReadyMs)), launchToReadyMedianMs: median(samples.map(item => item.launchToReadyMs)), startupJsBytes, builtJsFiles: assets.filter(name => name.endsWith('.js')), samples,
  }
  await fs.mkdir(path.dirname(output), { recursive: true })
  await fs.writeFile(output, JSON.stringify(report, null, 2) + '\n')
  process.stdout.write(`Saved ${output}\n`)
}
main().catch(error => { console.error(error); process.exitCode = 1 })
