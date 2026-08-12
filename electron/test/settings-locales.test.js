const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const localesDir = path.join(__dirname, '..', 'renderer', 'i18n', 'locales')

function flattenMessages(value, prefix = '', result = {}) {
  for (const [key, child] of Object.entries(value)) {
    const childPath = prefix ? `${prefix}.${key}` : key
    if (child && typeof child === 'object' && !Array.isArray(child)) {
      flattenMessages(child, childPath, result)
    } else {
      result[childPath] = child
    }
  }
  return result
}

function interpolationVariables(value) {
  if (typeof value !== 'string') return []
  return [...value.matchAll(/\{\{([^}]+)\}\}/g)].map(match => match[1]).sort()
}

test('keeps every locale aligned with the English message catalog', () => {
  const english = JSON.parse(fs.readFileSync(path.join(localesDir, 'en', 'common.json'), 'utf8'))
  const englishMessages = flattenMessages(english)

  for (const locale of fs.readdirSync(localesDir).filter(locale => locale !== 'en')) {
    const filePath = path.join(localesDir, locale, 'common.json')
    const messages = flattenMessages(JSON.parse(fs.readFileSync(filePath, 'utf8')))

    for (const [key, englishValue] of Object.entries(englishMessages)) {
      assert.ok(key in messages, `${locale}: missing translation for ${key}`)
      assert.deepEqual(
        interpolationVariables(messages[key]),
        interpolationVariables(englishValue),
        `${locale}: interpolation variables differ for ${key}`,
      )
    }
  }
})

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
