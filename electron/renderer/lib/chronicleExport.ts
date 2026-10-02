import type { ChronicleChapter, CurrentEra, NarrativeSection } from '../hooks/useBackend'

type ChronicleExportTheme = 'stellaris-cyan' | 'tactica-green' | 'command-amber'

export interface ChronicleExportLabels {
  title: string
  chapter: string
  summary: string
  currentEra: string
  storyContinues: string
  present: string
  events: string
  footer: string
}

export interface ChronicleExportOptions {
  locale: string
  labels: ChronicleExportLabels
  theme?: string
  legacyChronicle?: string
}

interface ChronicleExportPalette {
  bgPrimary: string
  bgSecondary: string
  textPrimary: string
  textSecondary: string
  textSecondary40: string
  textSecondary70: string
  accent: string
  accent40: string
  accent50: string
  accent60: string
  border: string
  border50: string
  yellow: string
  yellow30: string
}

const EXPORT_PALETTES: Record<ChronicleExportTheme, ChronicleExportPalette> = {
  'stellaris-cyan': {
    bgPrimary: '#05080d',
    bgSecondary: '#0c1219',
    textPrimary: '#e8f4f8',
    textSecondary: '#7a8c99',
    textSecondary40: 'rgba(122,140,153,0.4)',
    textSecondary70: 'rgba(122,140,153,0.7)',
    accent: '#00d4ff',
    accent40: 'rgba(0,212,255,0.4)',
    accent50: 'rgba(0,212,255,0.5)',
    accent60: 'rgba(0,212,255,0.6)',
    border: '#1e3a5f',
    border50: 'rgba(30,58,95,0.5)',
    yellow: '#ecc94b',
    yellow30: 'rgba(236,201,75,0.3)',
  },
  'tactica-green': {
    bgPrimary: '#050705',
    bgSecondary: '#090e09',
    textPrimary: '#e0ffe0',
    textSecondary: '#7ca27c',
    textSecondary40: 'rgba(124,162,124,0.4)',
    textSecondary70: 'rgba(124,162,124,0.7)',
    accent: '#7cff5b',
    accent40: 'rgba(124,255,91,0.4)',
    accent50: 'rgba(124,255,91,0.5)',
    accent60: 'rgba(124,255,91,0.6)',
    border: '#2c532c',
    border50: 'rgba(44,83,44,0.5)',
    yellow: '#e0c364',
    yellow30: 'rgba(224,195,100,0.3)',
  },
  'command-amber': {
    bgPrimary: '#0b0906',
    bgSecondary: '#120e08',
    textPrimary: '#fff3e0',
    textSecondary: '#b19572',
    textSecondary40: 'rgba(177,149,114,0.4)',
    textSecondary70: 'rgba(177,149,114,0.7)',
    accent: '#ffc857',
    accent40: 'rgba(255,200,87,0.4)',
    accent50: 'rgba(255,200,87,0.5)',
    accent60: 'rgba(255,200,87,0.6)',
    border: '#604622',
    border50: 'rgba(96,70,34,0.5)',
    yellow: '#ffd880',
    yellow30: 'rgba(255,216,128,0.3)',
  },
}

function resolveExportTheme(rawTheme: string | null | undefined): ChronicleExportTheme {
  if (rawTheme === 'tactica-phosphor') {
    return 'tactica-green'
  }
  if (rawTheme === 'tactica-green' || rawTheme === 'command-amber') {
    return rawTheme
  }
  return 'stellaris-cyan'
}

function replaceAllCompat(input: string, needle: string, replacement: string): string {
  return input.split(needle).join(replacement)
}

function applyExportTheme(css: string, theme: ChronicleExportTheme): string {
  const palette = EXPORT_PALETTES[theme]
  return [
    ['#05080d', palette.bgPrimary],
    ['#0c1219', palette.bgSecondary],
    ['#e8f4f8', palette.textPrimary],
    ['#7a8c99', palette.textSecondary],
    ['rgba(122,140,153,0.4)', palette.textSecondary40],
    ['rgba(122,140,153,0.7)', palette.textSecondary70],
    ['#00d4ff', palette.accent],
    ['rgba(0,212,255,0.4)', palette.accent40],
    ['rgba(0,212,255,0.5)', palette.accent50],
    ['rgba(0,212,255,0.6)', palette.accent60],
    ['#1e3a5f', palette.border],
    ['rgba(30,58,95,0.5)', palette.border50],
    ['#ecc94b', palette.yellow],
    ['rgba(236,201,75,0.3)', palette.yellow30],
  ].reduce((acc, [needle, replacement]) => replaceAllCompat(acc, needle, replacement), css)
}

/**
 * Generate a self-contained HTML file for a chronicle export.
 * All styles are inlined — no external dependencies.
 */
export function generateChronicleHtml(
  empireName: string,
  chapters: ChronicleChapter[],
  currentEra: CurrentEra | null,
  options: ChronicleExportOptions,
): string {
  const css = applyExportTheme(CSS, resolveExportTheme(options.theme))
  const chaptersHtml = chapters.map(chapter => renderChapter(chapter, options)).join('\n')
  const currentEraHtml = currentEra ? renderCurrentEra(currentEra, options) : ''
  const legacyHtml = chapters.length === 0 && !currentEra && options.legacyChronicle?.trim()
    ? `<section class="chapter-panel narrative">${renderNarrativeText(options.legacyChronicle)}</section>`
    : ''
  const title = options.labels.title.replace('{empire}', empireName)
  const locale = /^(en|de|fr|es|pt-BR|ja|zh-Hans|en-XA)$/.test(options.locale) ? options.locale : 'en'

  return `<!DOCTYPE html>
<html lang="${locale}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(title)}</title>
<style>
${css}
</style>
</head>
<body>
<article class="chronicle">
  <header class="chronicle-header">
    <div class="header-diamond">&#x25C8;</div>
    <h1>${escapeHtml(title)}</h1>
    <div class="energy-line"></div>
  </header>

${chaptersHtml}
${currentEraHtml}
${legacyHtml}

  <footer class="chronicle-footer">
    <div class="energy-line"></div>
    <p>${escapeHtml(options.labels.footer)}</p>
  </footer>
</article>
</body>
</html>`
}

// ---------------------------------------------------------------------------
// CSS
// ---------------------------------------------------------------------------

const CSS = `
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: #05080d;
  color: #e8f4f8;
  font-family: Rajdhani, -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  font-size: 16px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  overflow-wrap: break-word;
}
html:lang(ja) body { font-family: -apple-system, BlinkMacSystemFont, 'Hiragino Sans', 'Yu Gothic', 'Noto Sans JP', sans-serif; line-break: strict; }
html:lang(zh-Hans) body { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif; line-break: strict; }
html:lang(ja) .chapter-label, html:lang(ja) .current-era-label, html:lang(ja) .chronicle-footer,
html:lang(zh-Hans) .chapter-label, html:lang(zh-Hans) .current-era-label, html:lang(zh-Hans) .chronicle-footer { letter-spacing: normal; }
html:lang(ja) .chronicle-header h1, html:lang(zh-Hans) .chronicle-header h1 { font-family: inherit; letter-spacing: normal; text-transform: none; }
html:lang(ja) .drop-cap::first-letter, html:lang(zh-Hans) .drop-cap::first-letter { float: none; font-size: inherit; line-height: inherit; padding: 0; color: inherit; }

.chronicle {
  max-width: 800px;
  margin: 0 auto;
  padding: 48px 24px;
}

/* Header */
.chronicle-header {
  text-align: center;
  margin-bottom: 48px;
}
.header-diamond {
  font-size: 1.875rem;
  color: #00d4ff;
  margin-bottom: 12px;
}
.chronicle-header h1 {
  font-family: Orbitron, Rajdhani, sans-serif;
  font-size: 1.5rem;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: #e8f4f8;
  font-weight: 600;
}

/* Energy line divider */
.energy-line {
  height: 1px;
  max-width: 200px;
  margin: 16px auto;
  background: linear-gradient(90deg, transparent, rgba(0,212,255,0.5), transparent);
}

/* Chapter panel */
.chapter-panel {
  background: #0c1219;
  border: 1px solid #1e3a5f;
  border-radius: 8px;
  padding: 32px;
  margin-bottom: 32px;
  position: relative;
}

/* Chapter header */
.chapter-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: #00d4ff;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.chapter-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #e8f4f8;
  margin-bottom: 8px;
}
.chapter-dates {
  font-size: 0.875rem;
  color: #7a8c99;
  font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
}
.chapter-header-block {
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid #1e3a5f;
}

/* Narrative prose */
.narrative p {
  margin-bottom: 16px;
}
.narrative p:last-child {
  margin-bottom: 0;
}

/* Inline formatting */
.narrative strong {
  color: #00d4ff;
  font-weight: 600;
}
.narrative em {
  font-style: italic;
}
.narrative q {
  font-style: italic;
  color: #7a8c99;
}

/* Epigraph */
.epigraph {
  text-align: center;
  font-style: italic;
  color: #7a8c99;
  margin-bottom: 32px;
  padding-bottom: 24px;
  border-bottom: 1px solid rgba(30,58,95,0.5);
}

/* Scene break */
.scene-break {
  text-align: center;
  color: rgba(122,140,153,0.4);
  margin: 24px 0;
  font-size: 0.875rem;
  letter-spacing: 0.5em;
}

/* Blockquote */
.chronicle-quote {
  border-left: 3px solid rgba(0,212,255,0.4);
  padding-left: 16px;
  margin: 16px 0;
  font-style: italic;
  color: #7a8c99;
}
.chronicle-quote footer {
  font-size: 0.875rem;
  color: rgba(122,140,153,0.7);
  font-style: normal;
  margin-top: 8px;
}

/* Declaration */
.declaration {
  text-align: center;
  margin: 24px 0;
  padding: 16px 0;
  border-top: 1px solid rgba(236,201,75,0.3);
  border-bottom: 1px solid rgba(236,201,75,0.3);
}
.declaration p {
  font-size: 0.875rem;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  color: #ecc94b;
  font-weight: 600;
  margin: 0;
}

/* Summary */
.chapter-summary {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #1e3a5f;
}
.chapter-summary h4 {
  font-size: 0.75rem;
  font-weight: 600;
  color: #7a8c99;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.chapter-summary h4 span {
  color: rgba(0,212,255,0.6);
}
.chapter-summary p {
  font-size: 0.875rem;
  color: #7a8c99;
  line-height: 1.6;
}

/* Current era */
.current-era-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: #ecc94b;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.current-era-footer {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #1e3a5f;
  font-size: 0.75rem;
  color: #7a8c99;
  display: flex;
  align-items: center;
  gap: 8px;
}
.current-era-footer span:first-child {
  color: #00d4ff;
}

/* Markdown headers in narrative */
.narrative h2 {
  font-size: 1.25rem;
  font-weight: 600;
  color: #e8f4f8;
  margin-top: 32px;
  margin-bottom: 16px;
}
.narrative h3 {
  font-size: 1.125rem;
  font-weight: 600;
  color: #e8f4f8;
  margin-top: 32px;
  margin-bottom: 12px;
}
.narrative h4 {
  font-size: 1rem;
  font-weight: 600;
  color: #e8f4f8;
  margin-top: 24px;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.narrative h4 .sub-marker {
  color: rgba(0,212,255,0.4);
  font-size: 0.875rem;
}

/* Footer */
.chronicle-footer {
  text-align: center;
  margin-top: 48px;
  color: #7a8c99;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
.chronicle-footer p {
  margin-top: 12px;
}

/* Drop cap for first prose section */
.drop-cap::first-letter {
  float: left;
  font-size: 3.5em;
  line-height: 0.8;
  padding-right: 8px;
  padding-top: 4px;
  color: #00d4ff;
  font-weight: 700;
}
`

// ---------------------------------------------------------------------------
// Chapter rendering
// ---------------------------------------------------------------------------

function renderChapter(chapter: ChronicleChapter, options: ChronicleExportOptions): string {
  const title = cleanTitle(chapter.title)
  const narrative = chapter.sections?.length
    ? renderSections(chapter.sections, chapter.epigraph)
    : chapter.narrative ? renderNarrativeText(chapter.narrative) : ''

  const summary = chapter.summary
    ? `<div class="chapter-summary">
    <h4><span>&#x25C7;</span> ${escapeHtml(options.labels.summary)}</h4>
    <p>${escapeHtml(chapter.summary)}</p>
  </div>`
    : ''

  return `  <section class="chapter-panel">
    <div class="chapter-header-block">
      <div class="chapter-label"><span>&#x25C7;</span> ${escapeHtml(options.labels.chapter.replace('{number}', options.locale === 'en' ? toRoman(chapter.number) : new Intl.NumberFormat(options.locale).format(chapter.number)))}</div>
      <div class="chapter-title">${escapeHtml(title)}</div>
      <div class="chapter-dates">${escapeHtml(chapter.start_date)} &ndash; ${escapeHtml(chapter.end_date)}</div>
    </div>
    <div class="narrative">
${narrative}
    </div>
${summary}
  </section>`
}

function renderCurrentEra(era: CurrentEra, options: ChronicleExportOptions): string {
  const narrative = era.sections?.length
    ? renderSections(era.sections)
    : era.narrative ? renderNarrativeText(era.narrative) : ''

  return `  <section class="chapter-panel">
    <div class="chapter-header-block">
      <div class="current-era-label"><span>&#x231B;</span> ${escapeHtml(options.labels.currentEra)}</div>
      <div class="chapter-title">${escapeHtml(options.labels.storyContinues)}</div>
      <div class="chapter-dates">${escapeHtml(era.start_date)} &ndash; ${escapeHtml(era.coverage_date || options.labels.present)}</div>
    </div>
    <div class="narrative">
${narrative}
    </div>
    <div class="current-era-footer">
      <span>&#x25C7;</span>
      <span>${escapeHtml(options.labels.events.replace('{count}', new Intl.NumberFormat(options.locale).format(era.events_covered)))}</span>
    </div>
  </section>`
}

// ---------------------------------------------------------------------------
// Sections rendering (structured format)
// ---------------------------------------------------------------------------

function renderSections(sections: NarrativeSection[], epigraph?: string): string {
  const parts: string[] = []

  if (epigraph) {
    parts.push(`      <div class="epigraph"><p>${escapeHtml(epigraph)}</p></div>`)
  }

  let isFirstProse = true

  sections.forEach((section, i) => {
    if (i > 0) {
      parts.push('      <div class="scene-break">*</div>')
    }

    switch (section.type) {
      case 'prose': {
        const cls = isFirstProse ? ' class="drop-cap"' : ''
        parts.push(`      <p${cls}>${formatInline(section.text)}</p>`)
        isFirstProse = false
        break
      }
      case 'quote': {
        const attribution = section.attribution
          ? `\n        <footer>&mdash; ${escapeHtml(section.attribution)}</footer>`
          : ''
        parts.push(`      <blockquote class="chronicle-quote">
        <p>${formatInline(section.text)}</p>${attribution}
      </blockquote>`)
        break
      }
      case 'declaration':
        parts.push(`      <div class="declaration"><p>${escapeHtml(section.text)}</p></div>`)
        break
    }
  })

  return parts.join('\n')
}

// ---------------------------------------------------------------------------
// Narrative text rendering (legacy flat format)
// ---------------------------------------------------------------------------

function renderNarrativeText(text: string): string {
  if (!text) return ''

  const paragraphs = text.split(/\n\n+/)
  const parts: string[] = []

  for (const raw of paragraphs) {
    const para = raw.trim()
    if (!para) continue

    if (para.startsWith('### ')) {
      parts.push(`      <h4><span class="sub-marker">&rsaquo;</span> ${escapeHtml(para.slice(4))}</h4>`)
    } else if (para.startsWith('## ')) {
      parts.push(`      <h3>${escapeHtml(para.slice(3))}</h3>`)
    } else if (para.startsWith('# ')) {
      parts.push(`      <h2>${escapeHtml(para.slice(2))}</h2>`)
    } else if (para.startsWith('===') || para.startsWith('---')) {
      parts.push('      <div class="energy-line" style="max-width:100%;margin:32px auto"></div>')
    } else {
      parts.push(`      <p>${formatInline(para)}</p>`)
    }
  }

  return parts.join('\n')
}

// ---------------------------------------------------------------------------
// Inline formatting: **bold**, *italic*, "quotes"
// ---------------------------------------------------------------------------

function formatInline(text: string): string {
  let s = escapeHtml(text.replace(/\n/g, ' '))

  // Bold **text** → <strong>
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  // Italic *text* (not preceded/followed by *)
  s = s.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>')
  // Quoted "text" → <q>
  s = s.replace(/&quot;([^&]+?)&quot;/g, '<q>$1</q>')

  return s
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function toRoman(num: number): string {
  const numerals: [number, string][] = [
    [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I'],
  ]
  let result = ''
  let remaining = num
  for (const [value, numeral] of numerals) {
    while (remaining >= value) {
      result += numeral
      remaining -= value
    }
  }
  return result
}

function cleanTitle(title: string): string {
  return title.replace(/^Chapter\s+\w+:\s*/i, '')
}
