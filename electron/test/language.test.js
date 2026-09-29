const assert = require('node:assert/strict')
const test = require('node:test')
const { normalizeLanguage, resolveLanguage, changesBackendConfiguration, trayCacheKey } = require('../main/language')

test('explicit language, aliases and system locale resolution are stable', () => {
  assert.equal(normalizeLanguage('pt_BR'), 'pt-BR')
  assert.equal(normalizeLanguage('zh-CN'), 'zh-Hans')
  assert.equal(normalizeLanguage('xx'), 'system')
  assert.equal(resolveLanguage('ja', 'en-US'), 'ja')
  assert.equal(resolveLanguage('system', 'ja-JP'), 'ja')
  assert.equal(resolveLanguage('system', 'zh-SG'), 'zh-Hans')
  assert.equal(resolveLanguage('system', 'pt-PT'), 'pt-BR')
  assert.equal(resolveLanguage('system', 'it-IT'), 'en')
})

test('language-only saves cannot configure or restart the backend', () => {
  assert.equal(changesBackendConfiguration({ language: 'ja' }), false)
  assert.equal(changesBackendConfiguration({ language: 'system' }), false)
  assert.equal(changesBackendConfiguration({ language: 'de', uiTheme: 'command-amber' }), false)
  assert.equal(changesBackendConfiguration({ saveDir: '/tmp/fictional-saves' }), true)
  assert.equal(changesBackendConfiguration({ playerName: 'Fictional Empire' }), true)
})

test('tray cache changes when locale changes without a connection change', () => {
  assert.notEqual(trayCacheKey('ja', 'connected'), trayCacheKey('de', 'connected'))
  assert.equal(trayCacheKey('ja', 'connected'), trayCacheKey('ja', 'connected'))
})
