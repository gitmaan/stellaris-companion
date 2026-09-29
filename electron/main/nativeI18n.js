const fs = require('node:fs')
const path = require('node:path')

const catalogs = new Map()
const supported = new Set(['en', 'de', 'fr', 'es', 'pt-BR', 'ja', 'zh-Hans', 'en-XA'])

function catalog(locale) {
  const normalized = supported.has(locale) ? locale : 'en'
  if (catalogs.has(normalized)) return catalogs.get(normalized)
  try {
    const file = path.join(__dirname, '..', 'renderer', 'i18n', 'locales', normalized, 'common.json')
    const messages = JSON.parse(fs.readFileSync(file, 'utf8'))
    catalogs.set(normalized, messages)
    return messages
  } catch {
    if (normalized !== 'en') return catalog('en')
    return {}
  }
}

function lookup(root, key) {
  return key.split('.').reduce((node, part) => node?.[part], root)
}

function nativeText(locale, key, values = {}) {
  const translated = lookup(catalog(locale), `native.${key}`)
  const fallback = lookup(catalog('en'), `native.${key}`)
  const template = typeof translated === 'string' ? translated : typeof fallback === 'string' ? fallback : key
  return template.replace(/\{(\w+)\}/g, (match, name) => values[name] === undefined ? match : String(values[name]))
}

module.exports = { nativeText }
