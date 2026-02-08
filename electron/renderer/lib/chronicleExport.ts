import type { ChronicleChapter, CurrentEra, NarrativeSection } from '../hooks/useBackend'

/**
 * Generate a self-contained HTML file for a chronicle export.
 * All styles are inlined — no external dependencies.
 */
export function generateChronicleHtml(
  empireName: string,
  chapters: ChronicleChapter[],
  currentEra: CurrentEra | null,
): string {
  const chaptersHtml = chapters.map(renderChapter).join('\n')
  const currentEraHtml = currentEra ? renderCurrentEra(currentEra) : ''

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chronicles of ${escapeHtml(empireName)}</title>
<style>
${CSS}
</style>
</head>
<body>
<article class="chronicle">
  <header class="chronicle-header">
    <div class="header-diamond">&#x25C8;</div>
    <h1>The Chronicles of ${escapeHtml(empireName)}</h1>
    <div class="energy-line"></div>
  </header>

${chaptersHtml}
${currentEraHtml}

  <footer class="chronicle-footer">
    <div class="energy-line"></div>
    <p>Exported from Stellaris Companion</p>
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
}

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

function renderChapter(chapter: ChronicleChapter): string {
  const title = cleanTitle(chapter.title)
  const narrative = chapter.sections?.length
    ? renderSections(chapter.sections, chapter.epigraph)
    : chapter.narrative ? renderNarrativeText(chapter.narrative) : ''

  const summary = chapter.summary
    ? `<div class="chapter-summary">
    <h4><span>&#x25C7;</span> Summary</h4>
    <p>${escapeHtml(chapter.summary)}</p>
  </div>`
    : ''

  return `  <section class="chapter-panel">
    <div class="chapter-header-block">
      <div class="chapter-label"><span>&#x25C7;</span> Chapter ${escapeHtml(toRoman(chapter.number))}</div>
      <div class="chapter-title">${escapeHtml(title)}</div>
      <div class="chapter-dates">${escapeHtml(chapter.start_date)} &ndash; ${escapeHtml(chapter.end_date)}</div>
    </div>
    <div class="narrative">
${narrative}
    </div>
${summary}
  </section>`
}

function renderCurrentEra(era: CurrentEra): string {
  const narrative = era.sections?.length
    ? renderSections(era.sections)
    : era.narrative ? renderNarrativeText(era.narrative) : ''

  return `  <section class="chapter-panel">
    <div class="chapter-header-block">
      <div class="current-era-label"><span>&#x231B;</span> The Current Era</div>
      <div class="chapter-title">The Story Continues...</div>
      <div class="chapter-dates">${escapeHtml(era.start_date)} &ndash; Present</div>
    </div>
    <div class="narrative">
${narrative}
    </div>
    <div class="current-era-footer">
      <span>&#x25C7;</span>
      <span>${era.events_covered} events in this era</span>
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
