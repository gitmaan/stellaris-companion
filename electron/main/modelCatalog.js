const fs = require('node:fs')
const path = require('node:path')

// The same family definitions ship in the Python package and as an Electron resource.
const catalogPath = process.resourcesPath && path.join(process.resourcesPath, 'model_catalog.json')
const modelCatalog = JSON.parse(fs.readFileSync(
  catalogPath && fs.existsSync(catalogPath) ? catalogPath : path.join(__dirname, '../../stellaris_companion/model_catalog.json'),
  'utf8',
))

function selectionFamily(model, provider) {
  if (!model.startsWith(modelCatalog.selectionPrefix)) return null
  const family = model.slice(modelCatalog.selectionPrefix.length)
  if (!modelCatalog.families[family]?.patterns[provider]) throw new Error('This latest-stable model family is not supported by the provider.')
  return family
}

function stableFamilyModels(entries, provider, family, today = new Date().toISOString().slice(0, 10)) {
  const pattern = modelCatalog.families[family]?.patterns[provider]
  if (!pattern) return []
  const seen = new Set()
  const candidates = []
  for (const entry of entries) {
    if (!entry || typeof entry !== 'object') continue
    const id = String(entry.id || entry.name || '').replace(/^models\//, '')
    const match = new RegExp(pattern).exec(id)
    const label = String(entry.display_name || entry.displayName || entry.name || '')
    if (!match || seen.has(id) || /\b(preview|experimental|exp|beta|alpha|deprecated)\b/i.test(label)) continue
    if (entry.expiration_date) {
      const expiry = String(entry.expiration_date).slice(0, 10)
      if (!/^\d{4}-\d{2}-\d{2}$/.test(expiry) || !Number.isFinite(Date.parse(expiry))
        || new Date(expiry).toISOString().slice(0, 10) !== expiry || expiry <= today) continue
    }
    if (provider === 'openrouter') {
      if (Array.isArray(entry.architecture?.output_modalities) && !entry.architecture.output_modalities.includes('text')) continue
      if (Array.isArray(entry.endpoints) && !entry.endpoints.includes('/api/v1/chat/completions')) continue
    } else {
      const actions = entry.supported_actions || entry.supportedGenerationMethods
      if (!Array.isArray(actions) || !actions.includes('generateContent')) continue
    }
    const version = [...match[1].split('.').map(Number), 0, 0, 0].slice(0, 3)
    const rank = [...version, Number(match[2] || 0), typeof entry.created === 'number' ? entry.created : 0]
    candidates.push({ rank, entry: { ...entry, id } })
    seen.add(id)
  }
  candidates.sort((a, b) => {
    for (let i = 0; i < a.rank.length; i++) if (a.rank[i] !== b.rank[i]) return b.rank[i] - a.rank[i]
    return b.entry.id.localeCompare(a.entry.id)
  })
  return candidates.map(item => item.entry)
}

module.exports = { modelCatalog, selectionFamily, stableFamilyModels }
