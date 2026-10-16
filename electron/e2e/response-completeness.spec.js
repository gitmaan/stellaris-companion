const fs = require('node:fs/promises')
const os = require('node:os')
const path = require('node:path')
const { test, expect, _electron: electron } = require('@playwright/test')
const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')
const zh = require('../renderer/i18n/locales/zh-Hans/common.json')

async function withApp(backend, run, { scale = 1, uiScale = 1 } = {}) {
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-completion-e2e-'))
  let app
  try {
    await fs.writeFile(path.join(profile, 'settings.json'), JSON.stringify({ language: 'zh-Hans', uiScale }))
    app = await electron.launch({
      args: [`--force-device-scale-factor=${scale}`, ...getElectronLaunchArgs(path.resolve(__dirname, '../main.js'))],
      env: { ...process.env, NODE_ENV: 'test', E2E: '1', E2E_ONBOARDING_COMPLETE: '1',
        E2E_BACKEND_CONFIGURED: '1', E2E_SKIP_BACKEND_AUTOSTART: '1', E2E_FAKE_SECURE_STORAGE: '1',
        E2E_HEALTH_CHECK_INTERVAL_MS: '200', E2E_USER_DATA_DIR: profile,
        STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'completion-test-token' },
    })
    // Exercise the real renderer/preload/main Copy path without changing the user's clipboard.
    await app.evaluate(({ clipboard }) => {
      clipboard.writeText = text => { globalThis.__completionCopiedText = text }
    })
    const page = await app.firstWindow()
    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-Hans')
    await expect(page.locator('#page-chat textarea')).toBeEnabled()
    await run(page, app)
  } finally {
    if (app) await app.close()
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
}

test('partial answers survive reload and retry with a fresh request while remaining copyable', async ({}, testInfo) => {
  const partial = '这是尚未完成的战略建议：先检查合金产量，然后'
  const complete = '这是完整的战略建议。检查合金产量，并在扩张之前保留能源储备。'
  let count = 0
  const backend = createMockChronicleBackend({
    onChat: () => ++count === 1 ? partial : complete,
    chatCompletion: (_body, attempt) => ({ status: attempt === 1 ? 'truncated' : 'complete',
      finish_reason: attempt === 1 ? 'length' : 'stop', attempts: 2, recovered: attempt !== 1 }),
  })
  await withApp(backend, async (page, app) => {
    await page.locator('#page-chat textarea').fill('请分析当前战略。')
    await page.locator('#page-chat textarea').press('Enter')
    await expect(page.getByText(partial, { exact: true })).toBeVisible()
    await expect(page.getByText(zh.chat.message.incomplete, { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByText(zh.chat.message.incomplete, { exact: true })).toBeVisible()
    const partialMessage = page.locator('[data-message-id]').filter({ hasText: partial })
    await partialMessage.getByRole('button', { name: zh.visualQuality.copy, exact: true }).click()
    expect(await app.evaluate(() => globalThis.__completionCopiedText)).toBe(partial)
    await page.screenshot({ path: testInfo.outputPath('zh-incomplete-answer.png') })
    await page.getByRole('button', { name: zh.chat.message.retryIncomplete, exact: true }).click()
    await expect(page.getByText(complete, { exact: true })).toBeVisible()
    await expect(page.getByText(partial, { exact: true })).toBeVisible()
    const requests = backend.getChatRequests()
    expect(requests).toHaveLength(2)
    expect(requests[0].request_id).not.toBe(requests[1].request_id)
    expect(requests[0].message).toBe(requests[1].message)
    await page.reload()
    await expect(page.getByText(complete, { exact: true })).toBeVisible()
    await expect(page.locator('[data-completion-status="truncated"]')).toHaveCount(1)
  })
})

const paragraphs = Array.from({ length: 36 }, (_, i) =>
  `第${i + 1}段。` + '星际帝国的经济需要稳定的能源和合金供给。请检查每颗殖民星的岗位、住房和舒适度，再根据实际储备安排舰队建设。边境防御应与外交关系共同考虑，避免在资源不足时同时开启多个扩张计划。'.repeat(3))
const sentinel = '最终校验：全文已完整显示。'
const answer = `## 战略报告\n\n${paragraphs.join('\n\n')}\n\n${sentinel}`

async function waitForChatLayout(page, contentSize, zoom) {
  // Native setSize returns before the renderer resize and virtual-list measurements.
  // Let the resize finish before testing a subsequent, explicit user scroll.
  await expect.poll(() => page.evaluate(({ contentSize, zoom }) =>
    Math.abs(innerWidth * zoom - contentSize[0]) <= zoom
      && Math.abs(innerHeight * zoom - contentSize[1]) <= zoom,
  { contentSize, zoom })).toBe(true)
  await page.evaluate(async () => {
    await document.fonts.ready
    let previous = '', stableFrames = 0
    for (let frame = 0; frame < 90; frame++) {
      await new Promise(resolve => requestAnimationFrame(resolve))
      const scroller = document.querySelector('[data-chat-scroll]')
      const message = document.querySelector('[data-message-id="long-answer"]')
      if (!scroller || !message) { stableFrames = 0; previous = ''; continue }
      const bounds = message.getBoundingClientRect()
      const current = [scroller.clientWidth, scroller.clientHeight, scroller.scrollHeight,
        scroller.scrollTop, bounds.width, bounds.height].join(',')
      stableFrames = current === previous ? stableFrames + 1 : 0
      if (stableFrames >= 3) return
      previous = current
    }
    throw new Error('Chat layout did not settle after native resize')
  })
}

for (const scenario of [{ scale: 1, uiScale: 1 }, { scale: 1.25, uiScale: 1 }, { scale: 1.5, uiScale: 1.25 }]) {
  test(`long Chinese history remains readable and copyable at display ${scenario.scale} / app ${scenario.uiScale}`, async ({}, testInfo) => {
    test.setTimeout(90_000)
    const turns = Array.from({ length: 155 }, (_, i) => ({ id: `history-${i}`, request_id: `history-${i}`,
      question: `历史问题${i}`, answer: `历史回答${i}。`, created_at: 1700000000 + i, language: 'zh-Hans' }))
    turns.push({ id: 'long-answer', request_id: 'long-answer', question: '详细分析战略。', answer,
      created_at: 1700000200, language: 'zh-Hans', completion: { status: 'complete', finish_reason: 'stop', attempts: 1 } })
    const backend = createMockChronicleBackend({ conversations: [{ id: 'long-chat', save_id: 'save-1',
      title: '战略记录', created_at: 1, updated_at: 2, turns }] })
    await withApp(backend, async (page, app) => {
      const message = page.locator('[data-message-id="long-answer"]')
      const scroller = page.locator('[data-chat-scroll]')
      await expect(message).toBeVisible()
      const actualScale = await page.evaluate(() => devicePixelRatio)
      const actualZoom = await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.getZoomFactor())
      expect(actualZoom).toBeCloseTo(scenario.uiScale, 2)
      expect(actualScale).toBeCloseTo(scenario.scale * scenario.uiScale, 2)
      for (const size of [[1280, 900], [800, 700], [1600, 1000]]) {
        const contentSize = await app.evaluate(({ BrowserWindow }, [width, height]) => {
          const window = BrowserWindow.getAllWindows()[0]
          window.setSize(width, height)
          return window.getContentSize()
        }, size)
        await waitForChatLayout(page, contentSize, actualZoom)
        await expect(message.locator('.markdown-content p')).toHaveCount(paragraphs.length + 1)
        const blocks = message.locator('.markdown-content p')
        for (let index = 0; index <= paragraphs.length; index++) {
          const block = blocks.nth(index)
          await block.evaluate(element => element.scrollIntoView({ block: 'center', behavior: 'instant' }))
          await expect.poll(() => block.evaluate(element => {
            const bounds = element.getBoundingClientRect()
            const viewport = element.closest('[data-chat-scroll]').getBoundingClientRect()
            const bubble = element.closest('[data-message-id]').getBoundingClientRect()
            return bounds.top >= viewport.top - 1 && bounds.bottom <= viewport.bottom + 1
              && bounds.left >= bubble.left && bounds.right <= bubble.right + 1
              && bounds.left >= viewport.left && bounds.right <= viewport.right + 1
              && viewport.right <= innerWidth + 1
              && element.scrollWidth <= element.clientWidth + 1
          })).toBe(true)
        }
        await expect(message.getByText(sentinel, { exact: true })).toBeVisible()
        await message.getByRole('button', { name: zh.visualQuality.copy, exact: true }).click()
        expect(await app.evaluate(() => globalThis.__completionCopiedText)).toBe(answer)
        expect(await scroller.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true)
        expect(await page.locator('[data-message-id]').count()).toBeLessThan(40)
      }
      await message.getByText(sentinel, { exact: true }).evaluate(element =>
        element.scrollIntoView({ block: 'center', behavior: 'instant' }))
      await expect(message.getByText(sentinel, { exact: true })).toBeInViewport({ ratio: 1 })
      // CDP screenshots can crop zoomed Electron windows; capture the native surface.
      const png = await app.evaluate(async ({ BrowserWindow }) =>
        (await BrowserWindow.getAllWindows()[0].webContents.capturePage()).toPNG().toString('base64'))
      await fs.writeFile(testInfo.outputPath('zh-long-answer-end.png'), Buffer.from(png, 'base64'))
      await testInfo.attach('display-measurements', { body: JSON.stringify({ scenario, actualScale, actualZoom }), contentType: 'application/json' })
    }, scenario)
  })
}
