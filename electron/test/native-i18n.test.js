const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const { nativeText } = require('../main/nativeI18n')

test('native labels resolve in every production locale with safe fallback', () => {
  for (const locale of ['en', 'de', 'fr', 'es', 'pt-BR', 'ja', 'zh-Hans']) {
    assert.notEqual(nativeText(locale, 'tray.open'), 'tray.open')
    assert.ok(nativeText(locale, 'tray.status', { status: nativeText(locale, 'tray.connected') }).includes(nativeText(locale, 'tray.connected')))
    assert.notEqual(nativeText(locale, 'dialogs.selectSaveFolder'), 'dialogs.selectSaveFolder')
  }
  assert.equal(nativeText('unknown', 'tray.quit'), nativeText('en', 'tray.quit'))
  assert.match(nativeText('ja', 'crash.title'), /Stellaris Companion/)
})

test('native catalogs are listed in electron-builder files', () => {
  const config = fs.readFileSync(path.join(__dirname, '..', 'electron-builder.yml'), 'utf8')
  assert.match(config, /renderer\/i18n\/locales\/\*\*\/\*/)
})
