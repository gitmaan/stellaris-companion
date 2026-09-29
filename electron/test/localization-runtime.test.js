const assert = require('node:assert/strict')
const path = require('node:path')
const test = require('node:test')
const i18next = require(path.join(__dirname, '..', 'renderer', 'node_modules', 'i18next'))

const locales = ['en', 'de', 'fr', 'es', 'pt-BR', 'ja', 'zh-Hans']

test('runtime interpolation and plural selection work in every production locale', async () => {
  for (const locale of locales) {
    const messages = require(path.join(__dirname, '..', 'renderer', 'i18n', 'locales', locale, 'common.json'))
    const instance = i18next.createInstance()
    await instance.init({
      lng: locale,
      fallbackLng: false,
      initImmediate: false,
      resources: { [locale]: { translation: messages } },
      interpolation: { escapeValue: false },
    })
    for (const count of [0, 1, 2, 5]) {
      const saveCount = instance.t('onboarding.saves.count', { count })
      const pending = instance.t('chronicle.sidebar.pending', { count })
      assert.match(saveCount, new RegExp(String(count)), `${locale} save count ${count}`)
      assert.match(pending, new RegExp(String(count)), `${locale} pending chapters ${count}`)
      assert.doesNotMatch(saveCount + pending, /\{\{|onboarding\.saves|chronicle\.sidebar/, locale)
    }
    assert.ok(instance.t('chronicle.content.title', { empireName: '架空帝国' }).includes('架空帝国'))
    assert.notEqual(instance.t('report.categories.Bug'), 'report.categories.Bug')
  }
})
