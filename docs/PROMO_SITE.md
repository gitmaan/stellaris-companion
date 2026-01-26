# Stellaris Companion - Promo Site

## Stack
- **Framework**: Astro 6
- **Hosting**: Cloudflare Workers
- **Goal**: SEO/GEO optimized landing page

## Product Status
- **Stage**: Alpha
- **Primary Surface**: Electron app (Discord bot activates from within)
- **Platforms**: Windows, macOS
- **Distribution**: GitHub releases (open source for code inspection)
- **Pricing**: Free + BYOK (users provide own Gemini API key)

## Setup

```bash
npm create cloudflare@latest -- promo-site --framework=astro
cd promo-site
npx wrangler deploy
```

## Config

**astro.config.mjs**
```js
import { defineConfig } from 'astro/config';
import cloudflare from '@astrojs/cloudflare';

export default defineConfig({
  output: 'static',
  adapter: cloudflare(),
  site: 'https://stellaris-companion.com', // update with actual domain
});
```

**wrangler.jsonc**
```jsonc
{
  "name": "stellaris-companion-promo",
  "compatibility_date": "2025-04-01",
  "assets": {
    "directory": "./dist"
  }
}
```

## SEO Checklist
- [ ] Semantic HTML (proper headings, landmarks)
- [ ] JSON-LD structured data
- [ ] Open Graph / Twitter meta tags
- [ ] Sitemap (`@astrojs/sitemap`)
- [ ] Fast Core Web Vitals (LCP < 2.5s, CLS < 0.1)

## GEO (Generative Engine Optimization)

### Content Structure
- **Answer-first**: Value prop in first 40-60 words
- **Modular sections**: 75-300 words each, self-contained (AI extracts fragments)
- **Data density**: Stats every 150-200 words
- **Tables**: 2.5x citation boost — use for feature comparisons
- **Long-form**: 2000+ words on `/features` page

### Schema Markup (JSON-LD)
```json
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "Stellaris Companion",
  "applicationCategory": "GameApplication",
  "operatingSystem": "Windows, macOS",
  "description": "AI-powered strategic advisor for Stellaris",
  "offers": { "@type": "Offer", "price": "0", "priceCurrency": "USD" }
}
```
Also implement: `Organization`, `FAQPage` (28% more citations)

### Off-Site (Biggest Factor)
- [ ] Reddit presence (r/Stellaris, r/paradoxplaza) — Perplexity's #1 source
- [ ] Gaming blog coverage
- [ ] Wikidata entry for brand entity

### Technical
- LCP < 2s (AI crawlers timeout faster than browsers)
- Allow AI crawlers in robots.txt
- Semantic HTML5 elements

## Positioning

**Primary Message**: "Your empire's story, dramatically told"

**Secondary**: Strategic advice when you want it — not a crutch, a companion.

### The Anti-AI Gaming Context

The Stellaris/gaming community is skeptical of AI tools. Common concerns:
- "AI is cheating" / "takes the fun out of figuring it out"
- "soulless optimization" / "min-max robots"
- Data privacy / telemetry fears

**Our response**: This isn't an optimizer. It's a storyteller and companion.

### Positioning Pillars

| Pillar | Message |
|--------|---------|
| **Chronicle First** | Lead with storytelling. Dramatic narratives of YOUR campaign. |
| **Help When Needed** | Advisor is opt-in. Ask when stuck, ignore when you're in flow. |
| **Immersion > Optimization** | Ethics-based personality. Your advisor speaks like your empire. |
| **Privacy-Respecting** | Saves parsed locally. Only extracted context sent to Gemini. BYOK. |
| **Patch-Aware** | Knows your game version & DLCs. Won't suggest features you can't use. |

### Reframed Messaging

| Audience | Old (Optimizer) | New (Companion) |
|----------|-----------------|-----------------|
| Beginners | "Get advice based on YOUR empire" | "Never feel lost. Ask your advisor when you need a nudge." |
| Veterans | "Optimize faster with AI analysis" | "Chronicle your conquests. Get a second opinion on tough calls." |
| Roleplayers | "Speaks your empire's language" | "Your chronicler writes your empire's history in dramatic prose." |

### What We're NOT
- Not a cheat / exploit finder
- Not an auto-pilot / always-on optimizer
- Not a replacement for learning the game
- Not uploading your data anywhere

## Keywords

### Tier 1: Chronicle & Storytelling (Lead With)
- "stellaris story generator"
- "stellaris campaign chronicle"
- "stellaris empire history"
- "stellaris campaign story"
- "stellaris narrative"
- "stellaris roleplay tool"

### Tier 2: Companion / Advisor
- "stellaris AI companion"
- "stellaris advisor"
- "stellaris save analyzer"
- "stellaris help when stuck"

### Tier 3: Pain Points (Advisor Use Cases)
- "stellaris economy help"
- "stellaris why is my economy failing"
- "stellaris stuck mid game"
- "stellaris fleet composition help"
- "stellaris am I ready for crisis"

### Tier 4: Long-Tail
- "stellaris [situation] what to do"
- "stellaris my [resource] is negative"
- "stellaris should I [action] now"

## Pages

| Route | Purpose | Target Length |
|-------|---------|---------------|
| `/` | Hero, answer-first value prop, feature table, CTA | 500-800 words |
| `/features` | Deep dive, structured H2/H3, data tables | 2000+ words |
| `/faq` | 10-15 real questions with FAQPage schema | 1000+ words |
| `/chronicle` | Deep dive on Chronicle feature with examples | 1500+ words |
| `/guides/economy` | Evergreen SEO: economy management | 2000+ words |
| `/guides/fleet` | Evergreen SEO: fleet composition | 2000+ words |
| `/guides/crisis` | Evergreen SEO: crisis preparation | 2000+ words |
| `/privacy` | Basic privacy policy (Gemini data, BYOK) | Short |

## Page Content Outlines

### Homepage `/`
**H1**: Stellaris Companion — Chronicle Your Empire's Story

**Hero (first 60 words)**: Lead with Chronicle, not optimization
> Every empire has a story. Stellaris Companion transforms your campaign into dramatic chronicles — epic narratives of your conquests, alliances, and crises. Need strategic advice? Your ethics-aware advisor is there when you want it. Your saves are parsed locally.

**Sections**:
1. Chronicle Feature (hero section — dramatic narrative example)
2. How It Works (3-step: load save → generate chronicle → ask advisor)
3. Advisor When You Need It (not always-on — ask when stuck)
4. Empire Personality (ethics-based voice samples — show the fun)
5. Patch & DLC Aware (knows your version, won't suggest features you can't use)
6. Privacy (saves parsed locally, extracted context sent to Gemini, BYOK)
7. CTA: Try it with your save (GitHub releases link, version shown in footer)

**Tone**: Fun, immersive, companion — not "optimize your empire"

### Chronicle `/chronicle`
**H1**: Chronicle — Your Empire's Story in Dramatic Prose

**Hero**: Example chronicle excerpt (show, don't tell)
> "On the first day of 2491, the galaxy changed forever. The 'Militant Isolationists,' an ancient power long thought dormant, shook off the dust of millennia and awakened with a roar that shattered the peace..."

**Sections**:
1. What is Chronicle? — Dramatic, chapter-based narratives of YOUR campaign
2. How It Works — Events → Chapters → Epic Story
3. Voice Examples — Show Machine, Authoritarian, Egalitarian, etc. side-by-side
4. Recap Mode — "Previously on..." for returning to a campaign after a break
5. Sample Chronicles — Full examples from different empire types
6. CTA: Try it with your save

**Key Messaging**:
- Not a summary. A story.
- Your advisor is also your chronicler.
- Share your empire's legend.

### Features `/features`
**H1**: Features — Storytelling, Strategy, and Immersion

**Sections** (each 200-300 words, self-contained):

**Chronicle & Storytelling**
1. Empire Chronicles — Full campaign narratives in dramatic prose
2. Recap System — "Previously on..." summaries after breaks
3. Ethics-Based Voice — Machine, Authoritarian, Egalitarian voices sound different
4. Era Detection — Auto-names periods of your campaign history

**Strategic Advisor**
5. Ask When Stuck — Opt-in advice, not always-on optimization
6. Economy Help — Diagnose resource problems
7. Fleet Advice — Composition suggestions (not auto-builds)
8. Crisis Prep — Readiness checks before endgame

**Technical**
9. Patch & DLC Aware — Knows your version, won't suggest unavailable features
10. Privacy-Respecting — Saves parsed locally, only text context sent to Gemini API, BYOK
11. Mod Compatible — Works with modded saves
12. Multi-Platform — Windows, macOS

**Include**: Chronicle excerpt examples, personality voice samples, comparison table

### FAQ `/faq`
Implement FAQPage schema. Questions addressing community concerns + features:

**Chronicle & Fun**
1. What is the Chronicle feature?
2. How does the advisor's personality work?
3. Can I use it just for storytelling without the advisor?

**Anti-AI Concerns (Address Directly)**
4. Isn't this cheating?
   → No. It's opt-in advice when YOU ask. Like having a friend who knows the game.
5. Will it play the game for me?
   → No. It suggests, you decide. No automation, no auto-builds.
6. Does it ruin the fun of learning?
   → It's there when you're stuck, not hovering over your shoulder.

**Privacy & Data**
7. Does it upload my save files?
   → No. Saves are parsed locally on your machine.
8. What data IS sent to the AI?
   → Extracted text context (empire name, ethics, events, current state) is sent to Gemini API for processing. Not the raw save file.
9. Who sees my data?
   → Your Gemini API key = your Google account. We never see your data. Google's privacy policy applies.
10. Can I use my own API key?
   → Yes, required. BYOK (Bring Your Own Key) — we don't provide API access.

**Technical**
10. Does it work with mods?
11. What Stellaris versions are supported?
12. Does it know about the latest patch?
    → Yes. Detects your game version and DLCs. Won't suggest features you don't have.
13. Does it work with Machine Empires / Hive Minds?
14. Is it free?

### Guide Pages `/guides/*`
Evergreen SEO content targeting high-volume keywords. Each guide:
- 2000+ words
- Structured H2/H3
- Tables and data
- Ends with CTA: "Get personalized advice for YOUR game"

## Competitor Comparison (for Feature Table)

| Capability | Dashboards | Calculators | GPT Chatbots | **Stellaris Companion** |
|------------|------------|-------------|--------------|-------------------------|
| Reads save files | ✓ | ✗ | ✗ | ✓ |
| Strategic advice | ✗ | Limited | Generic | Personalized |
| Real-time updates | ✓ | ✗ | ✗ | ✓ |
| Adapts to empire | ✗ | ✗ | ✗ | ✓ |
| Answers "what next?" | ✗ | ✗ | Poorly | ✓ |
| Works with mods | Partial | N/A | ✗ | ✓ |
| Privacy-first | ✓ | N/A | ✗ | ✓ |

## Off-Site Strategy

### Reddit (Critical for Perplexity)

**Approach**: Lead with Chronicle/storytelling. Don't lead with "AI advisor" — the community is skeptical.

**Launch Posts**:
- [ ] r/Stellaris: Share a Chronicle output as content first (dramatic narrative of a campaign)
- [ ] Title angle: "I made a thing that writes dramatic chronicles of your Stellaris campaigns"
- [ ] Cross-post to r/paradoxplaza

**Ongoing Engagement**:
- [ ] Share interesting chronicle excerpts (show the fun)
- [ ] Engage in "what should I do" threads — mention the tool as optional help
- [ ] Don't be pushy. Provide value, let people discover.

**Address Anti-AI Sentiment**:
- Be upfront: "I know AI tools are controversial in gaming..."
- Emphasize: local-only, opt-in, storytelling focus
- Let the Chronicle speak for itself — if the narratives are good, people will care

### Other Channels
- [ ] Steam Community: Share chronicle output as a "story"
- [ ] Paradox Forums: Announce in modding/tools section
- [ ] Gaming blogs: Pitch the Chronicle angle (unique story)
- [ ] Wikidata entity for brand presence

### Content to Create for Reddit
- Chronicle examples from different empire types (Machine, Hive, Spiritualist, etc.)
- "Previously on..." recaps that look like TV show intros
- Screenshots of advisor personality (show the ethics-based voice differences)

## Launch Checklist

### Required for Launch
**Note**: Show version (e.g., "v0.1.0-alpha") in footer or download section, not in CTAs.


- [ ] Domain registered
- [ ] Astro site scaffolded with Cloudflare Workers
- [ ] Homepage with hero, features overview, CTA
- [ ] `/chronicle` page with examples
- [ ] `/faq` with FAQPage schema
- [ ] `/privacy` basic policy
- [ ] GitHub repo link for downloads
- [ ] Screenshots / GIFs of Electron app
- [ ] Chronicle example content (2-3 empire types)
- [ ] Open Graph / Twitter meta tags

### Nice to Have (Post-Launch)
- [ ] `/features` deep dive (2000+ words)
- [ ] Guide pages for SEO (`/guides/*`)
- [ ] Sitemap
- [ ] Analytics
- [ ] Wikidata entity

### Assets Needed
- [ ] Logo / icon
- [ ] App screenshots (Electron UI)
- [ ] Chronicle output examples
- [ ] Advisor personality voice samples (text)
- [ ] GIF of app in action (optional but high impact)
