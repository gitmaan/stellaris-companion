const LANGUAGE_PRESETS = ['system', 'en', 'de', 'fr', 'es', 'pt-BR', 'ja', 'zh-Hans', 'en-XA']
const DEFAULT_LANGUAGE = 'system'
const DEFAULT_RESOLVED_LANGUAGE = 'en'

function normalizeLanguage(rawValue) {
  if (typeof rawValue !== 'string') return DEFAULT_LANGUAGE
  const normalized = rawValue.trim()
  if (normalized === 'pt_BR') return 'pt-BR'
  if (['zh-CN', 'zh_CN', 'zh-Hans-CN'].includes(normalized)) return 'zh-Hans'
  return LANGUAGE_PRESETS.includes(normalized) ? normalized : DEFAULT_LANGUAGE
}

function resolveLanguage(language, osLocale = '') {
  const normalized = normalizeLanguage(language)
  if (normalized !== 'system') return normalized
  const locale = String(osLocale || '').trim().toLowerCase()
  if (locale.startsWith('pt')) return 'pt-BR'
  if (/^zh[-_](cn|sg|hans)/.test(locale) || locale === 'zh-hans') return 'zh-Hans'
  const base = locale.split(/[-_]/)[0]
  return ['en', 'de', 'fr', 'es', 'ja'].includes(base) ? base : DEFAULT_RESOLVED_LANGUAGE
}

const BACKEND_SETTINGS_KEYS = [
  'googleApiKey', 'openRouterApiKey', 'customProviderApiKey',
  'advisorProvider', 'advisorModel', 'advisorBaseUrl',
  'saveDir', 'savePath', 'modelRoutingMode',
  'playerName', 'playerCountryId',
]

function changesBackendConfiguration(changedSettings = {}) {
  return BACKEND_SETTINGS_KEYS.some(key => changedSettings[key] !== undefined)
}

function trayCacheKey(locale, status) {
  return `${locale}:${status}`
}

module.exports = { LANGUAGE_PRESETS, DEFAULT_LANGUAGE, DEFAULT_RESOLVED_LANGUAGE, normalizeLanguage, resolveLanguage, changesBackendConfiguration, trayCacheKey }
