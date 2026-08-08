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

test('keeps provider setup simple without overstating the connection probe', () => {
  const messages = JSON.parse(fs.readFileSync(path.join(localesDir, 'en', 'common.json'), 'utf8'))
  const advisor = messages.settings.advisor

  assert.ok(advisor.providerGroups.gemini)
  assert.ok(advisor.providerGroups.local)
  assert.ok(advisor.providerGroups.other)
  assert.match(advisor.modelReady, /structured responses supported/i)
  assert.doesNotMatch(advisor.modelReady, /advisor.*chronicle ready/i)
})
