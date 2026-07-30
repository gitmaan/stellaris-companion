const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const localesDir = path.join(__dirname, '..', 'renderer', 'i18n', 'locales')

test('ships complete update-channel and protected-storage copy in every locale', () => {
  for (const locale of fs.readdirSync(localesDir)) {
    const filePath = path.join(localesDir, locale, 'common.json')
    const messages = JSON.parse(fs.readFileSync(filePath, 'utf8'))
    const settings = messages.settings

    assert.ok(settings?.sections?.updates, `${locale}: missing Settings update section`)
    assert.ok(settings?.panels?.updateChannel, `${locale}: missing update panel title`)
    assert.ok(settings?.api?.storageWarning, `${locale}: missing credential warning`)
    assert.ok(settings?.updateChannel?.stable, `${locale}: missing Stable label`)
    assert.ok(settings?.updateChannel?.beta, `${locale}: missing Beta label`)
    assert.ok(settings?.updateChannel?.betaWarning, `${locale}: missing Beta warning`)
  }
})
