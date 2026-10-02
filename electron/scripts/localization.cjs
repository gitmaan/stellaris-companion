const fs = require('node:fs')
const path = require('node:path')

const root = path.join(__dirname, '..', 'renderer', 'i18n', 'locales')
const locales = ['de', 'fr', 'es', 'pt-BR', 'ja', 'zh-Hans']
const english = JSON.parse(fs.readFileSync(path.join(root, 'en', 'common.json'), 'utf8'))
const protectedWords = new Set(['Stellaris', 'Companion', 'ChatGPT', 'OpenAI', 'Gemini', 'Ollama', 'OpenRouter', 'LM', 'Studio', 'Claude', 'Codex', 'Cursor', 'Discord', 'GitHub', 'API', 'MCP', 'JSON', 'HTML', 'HTTPS', 'SQLite', 'Flash', 'Lite', 'AI', 'OS', 'K', 'MB'])
const accent = { a:'à', b:'ƀ', c:'ç', d:'ď', e:'ë', f:'ƒ', g:'ğ', h:'ĥ', i:'ï', j:'ĵ', k:'ķ', l:'ĺ', m:'ṁ', n:'ñ', o:'õ', p:'ṕ', q:'ɋ', r:'ŕ', s:'š', t:'ŧ', u:'ü', v:'ṽ', w:'ŵ', x:'ẋ', y:'ÿ', z:'ž' }

function pseudoString(input) {
  const pieces = input.split(/(\{\{[^{}]+\}\}|\{[^{}]+\}|https?:\/\/\S+|<[^>]+>)/g)
  return `［${pieces.map(piece => {
    if (/^(\{|https?:|<)/.test(piece)) return piece
    return piece.replace(/[A-Za-z]+/g, word => {
      if (protectedWords.has(word)) return word
      const out = [...word].map(char => {
        const replacement = accent[char.toLowerCase()] || char
        return char === char.toUpperCase() ? replacement.toUpperCase() : replacement
      }).join('')
      return `${out}${/[aeiou]/i.test(word) ? '~' : ''}`
    })
  }).join('')}］`
}

function pseudo(value) {
  if (Array.isArray(value)) return value.map(pseudo)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, pseudo(child)]))
  return typeof value === 'string' ? pseudoString(value) : value
}

function visit(value, callback, prefix = '') {
  if (Array.isArray(value)) value.forEach((child, index) => visit(child, callback, `${prefix}[${index}]`))
  else if (value && typeof value === 'object') for (const [key, child] of Object.entries(value)) visit(child, callback, prefix ? `${prefix}.${key}` : key)
  else callback(prefix, value)
}

function get(rootValue, key) {
  return key.replace(/\[(\d+)\]/g, '.$1').split('.').reduce((node, part) => node?.[part], rootValue)
}

function placeholders(value) {
  return [...String(value).matchAll(/\{\{([^{}]+)\}\}|(?<!\{)\{([^{}]+)\}(?!\})/g)].map(match => match[1] || match[2]).sort().join(',')
}

function validate(locale, data) {
  const errors = []
  const englishKeys = new Set()
  visit(english, (key, source) => {
    englishKeys.add(key)
    const target = get(data, key)
    if (target === undefined) { errors.push(`${key}: missing`); return }
    if (Array.isArray(source) !== Array.isArray(target) || typeof source !== typeof target) errors.push(`${key}: type mismatch`)
    if (typeof source === 'string' && placeholders(source) !== placeholders(target)) errors.push(`${key}: interpolation mismatch (${placeholders(source)} vs ${placeholders(target)})`)
  })
  const categories = new Intl.PluralRules(locale).resolvedOptions().pluralCategories
  visit(data, key => {
    if (englishKeys.has(key)) return
    const suffix = key.match(/_(\w+)$/)
    if (suffix && categories.includes(suffix[1]) && englishKeys.has(key.replace(/_\w+$/, '_other'))) return
    console.warn(`${locale}: unused key ${key}`)
  })
  for (const key of englishKeys) {
    if (!key.endsWith('_other')) continue
    const stem = key.slice(0, -6)
    for (const category of categories) {
      if (get(data, `${stem}_${category}`) === undefined) errors.push(`${stem}_${category}: required plural category`)
    }
  }
  return errors
}

const pseudoPath = path.join(root, 'en-XA', 'common.json')
const expectedPseudo = JSON.stringify(pseudo(english), null, 2) + '\n'
// Git may check text files out with CRLF on Windows; compare their content with stable newlines.
if (process.argv.includes('--write-pseudo')) fs.writeFileSync(pseudoPath, expectedPseudo)
else if (fs.readFileSync(pseudoPath, 'utf8').replace(/\r\n/g, '\n') !== expectedPseudo) {
  console.error('en-XA: pseudo-locale is out of date; run npm run localization:pseudo')
  process.exitCode = 1
}
for (const locale of locales) {
  const data = JSON.parse(fs.readFileSync(path.join(root, locale, 'common.json'), 'utf8'))
  const errors = validate(locale, data)
  if (errors.length) {
    console.error(`${locale}: ${errors.length} localization errors\n${errors.join('\n')}`)
    process.exitCode = 1
  } else console.log(`${locale}: complete`)
}

// Guard the workflows migrated in this tier against new unlocalized JSX copy.
// Product names, a provider key hint, and HTML entities are intentional literals.
const ts = require(path.join(__dirname, '..', 'renderer', 'node_modules', 'typescript'))
const migratedComponents = [
  'OnboardingModal', 'OnboardingAdvisorSetup', 'OnboardingFrame', 'AdvisorInfoPanel', 'ReportIssueModal', 'ErrorBoundary',
  'CampaignHistoryDialog', 'ChronicleContent', 'ChronicleChapterList',
  'ChatGPTConnection', 'ChatGPTWelcome', 'ChatGPTUsage',
]
const literalAllowlist = new Set(['Electron', '&gt;', 'AIza...'])
for (const component of migratedComponents) {
  const file = path.join(__dirname, '..', 'renderer', 'components', `${component}.tsx`)
  const source = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  function inspect(node) {
    const literal = ts.isJsxText(node) ? node.text.trim()
      : ts.isJsxAttribute(node) && ['title', 'aria-label', 'placeholder', 'alt'].includes(node.name.text) && node.initializer && ts.isStringLiteral(node.initializer) ? node.initializer.text.trim()
        : ''
    if (/[A-Za-z]{2,}/.test(literal) && !literalAllowlist.has(literal)) {
      const line = source.getLineAndCharacterOfPosition(node.pos).line + 1
      console.error(`${component}.tsx:${line}: untranslated JSX literal ${JSON.stringify(literal)}`)
      process.exitCode = 1
    }
    ts.forEachChild(node, inspect)
  }
  inspect(source)
}
