const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')
const { createSettingsStore } = require('../main/settingsStore')

function profile(t, saved) {
  const cwd = fs.mkdtempSync(path.join(os.tmpdir(), 'stellaris-routing-'))
  t.after(() => fs.rmSync(cwd, { recursive: true, force: true }))
  if (saved !== undefined) fs.writeFileSync(path.join(cwd, 'settings.json'), JSON.stringify(saved))
  return () => createSettingsStore({ cwd, projectVersion: '1.0.0' })
}

test('fresh installations persist Flash as the default across restart', t => {
  const open = profile(t)
  assert.equal(open().get('modelRoutingMode'), 'quality_first')
  assert.equal(open().get('modelRoutingMode'), 'quality_first')
})

test('legacy installations without a routing preference keep Lite across restart', t => {
  const open = profile(t, { advisorProvider: 'gemini', hasCompletedOnboarding: true })
  assert.equal(open().get('modelRoutingMode'), 'conserve')
  assert.equal(open().get('modelRoutingMode'), 'conserve')
})

for (const [saved, expected] of [
  ['conserve', 'conserve'], ['quality_first', 'quality_first'],
  ['flash-first', 'quality_first'], ['quota-saver', 'conserve'],
  [' FLASH_LITE_FIRST ', 'conserve'], ['free_tier', 'conserve'],
  ['unknown', 'conserve'], [null, 'conserve'],
]) {
  test(`upgrade preserves routing intent for ${JSON.stringify(saved)} and explicit models`, t => {
    const open = profile(t, { modelRoutingMode: saved, advisorModel: 'gemini-3.5-flash-lite' })
    const store = open()
    assert.equal(store.get('modelRoutingMode'), expected)
    assert.equal(store.get('advisorModel'), 'gemini-3.5-flash-lite')
    assert.equal(open().get('modelRoutingMode'), expected)
  })
}

test('a new user can choose Lite and keep it after restart', t => {
  const open = profile(t)
  open().set('modelRoutingMode', 'conserve')
  assert.equal(open().get('modelRoutingMode'), 'conserve')
})
