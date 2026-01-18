# Electron App - UI Specification

## Design Principles

1. **Game-Adjacent** - Feels like a companion app, not a productivity tool
2. **Dark Theme** - Matches Stellaris aesthetic, easier on eyes while gaming
3. **Information Dense** - Show relevant data without clutter
4. **Responsive** - Works at various window sizes (min 800x600)

## Color Palette

Based on Stellaris UI:

```css
:root {
  /* Background layers */
  --bg-primary: #0a0e14;      /* Deepest background */
  --bg-secondary: #131a24;    /* Card/panel background */
  --bg-tertiary: #1a2332;     /* Hover states, borders */

  /* Text */
  --text-primary: #e6edf3;    /* Main text */
  --text-secondary: #8b949e;  /* Secondary/muted text */
  --text-accent: #58a6ff;     /* Links, highlights */

  /* Accents */
  --accent-blue: #1f6feb;     /* Primary buttons, active states */
  --accent-green: #238636;    /* Success, positive */
  --accent-yellow: #d29922;   /* Warning, pending */
  --accent-red: #da3633;      /* Error, danger */
  --accent-purple: #8957e5;   /* Special/empire color */

  /* Borders */
  --border-default: #30363d;
  --border-subtle: #21262d;
}
```

## Typography

```css
:root {
  --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  --font-mono: 'SF Mono', Consolas, 'Liberation Mono', Menlo, monospace;

  --text-xs: 0.75rem;    /* 12px */
  --text-sm: 0.875rem;   /* 14px */
  --text-base: 1rem;     /* 16px */
  --text-lg: 1.125rem;   /* 18px */
  --text-xl: 1.25rem;    /* 20px */
  --text-2xl: 1.5rem;    /* 24px */
}
```

## Layout

### App Shell

```
┌─────────────────────────────────────────────────────────────┐
│ ← → ↺    Stellaris Companion           ─ □ ✕  │ (title bar)
├─────────────────────────────────────────────────────────────┤
│  StatusBar: United Nations of Earth | 2250.03.15 | ● Ready │
├────────────┬────────────────────────────────────────────────┤
│            │                                                │
│   [Chat]   │                                                │
│   [Recap]  │              Main Content Area                 │
│ [Settings] │                                                │
│            │                                                │
│            │                                                │
│            │                                                │
└────────────┴────────────────────────────────────────────────┘
```

- **Title Bar**: Native (hidden inset on macOS)
- **Status Bar**: Fixed top, shows empire + game date + backend status
- **Sidebar**: Fixed left, nav tabs with icons
- **Content**: Scrollable main area

### StatusBar Component

```
┌─────────────────────────────────────────────────────────────┐
│ 🌐 United Nations of Earth    📅 2250.03.15    ● Connected │
└─────────────────────────────────────────────────────────────┘
```

States:
- `● Connected` (green) - Backend healthy, save loaded
- `● Connecting...` (yellow) - Backend starting
- `● No Save` (yellow) - Backend healthy, no save loaded
- `● Disconnected` (red) - Backend not responding

### Chat Page

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ 👤 What should I research next?                     │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ 🤖 Based on your current situation...               │   │
│   │                                                     │   │
│   │ I recommend focusing on **Destroyers** in the      │   │
│   │ Engineering tree. This will give you...            │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│                        (scroll area)                        │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────┐  [Send]  │
│  │ Ask about your empire...                      │          │
│  └───────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

**Message Bubbles:**
- User: Right-aligned, accent color background
- Assistant: Left-aligned, secondary background
- Error: Left-aligned, red border
- Loading: Left-aligned, pulsing dots animation

### Settings Page

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   Settings                                                  │
│   ━━━━━━━━                                                  │
│                                                             │
│   API Configuration                                         │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ Google API Key (Gemini)                             │   │
│   │ ┌─────────────────────────────────────────────────┐ │   │
│   │ │ ••••••••••••••••                                │ │   │
│   │ └─────────────────────────────────────────────────┘ │   │
│   │ Get a key at Google AI Studio ↗                     │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   Save File Location                                        │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ ┌───────────────────────────────────┐  [Browse...] │   │
│   │ │ ~/Library/Stellaris/save games    │              │   │
│   │ └───────────────────────────────────┘              │   │
│   │ Leave empty to auto-detect                          │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   Discord Bot (Optional)                                    │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ ☐ Enable Discord bot                                │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│                                        [Save Settings]      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Recap Page

```
┌────────────────────────┬────────────────────────────────────┐
│                        │                                    │
│   Sessions             │   United Nations of Earth          │
│   ━━━━━━━━━            │   ━━━━━━━━━━━━━━━━━━━━━━━━━        │
│                        │                                    │
│   ● UNE (current)      │   Started: 2200.01.01              │
│     2200 → 2250        │   Current: 2250.03.15              │
│     45 snapshots       │   Snapshots: 45                    │
│                        │                                    │
│   ○ Blorg Commonality  │   [Generate Chapter Recap]         │
│     2200 → 2280        │                                    │
│     120 snapshots      │   ─────────────────────────────    │
│                        │                                    │
│   ○ Machine Empire     │   # The Rise of Humanity           │
│     2200 → 2310        │                                    │
│     180 snapshots      │   ## Early Expansion (2200-2220)   │
│                        │   The United Nations of Earth...   │
│                        │                                    │
│                        │   ## First Contact (2220-2235)     │
│                        │   ...                              │
│                        │                                    │
├────────────────────────┤                                    │
│ [End Current Session]  │                                    │
└────────────────────────┴────────────────────────────────────┘
```

## Components

### ChatMessage

Props:
- `role`: 'user' | 'assistant' | 'error' | 'loading'
- `content`: string (markdown for assistant)
- `timestamp?`: Date

Styling:
- User messages: `--accent-blue` background, right-aligned
- Assistant: `--bg-secondary` background, left-aligned
- Error: `--bg-secondary` with `--accent-red` left border
- Loading: Three bouncing dots animation

### ChatInput

Props:
- `onSend`: (message: string) => void
- `disabled`: boolean

Features:
- Auto-resize textarea (up to 4 lines)
- Send on Enter (Shift+Enter for newline)
- Disabled state during API call

### SessionList

Props:
- `sessions`: Session[]
- `selected`: Session | null
- `onSelect`: (session: Session) => void

Features:
- Active session has indicator dot
- Shows empire name, date range, snapshot count
- Scrollable if many sessions

### RecapViewer

Props:
- `recap`: string (markdown)

Features:
- Markdown rendering (headers, bold, lists)
- Scrollable content area
- Copy to clipboard button

### StatusBar

Props: None (uses hook)

Features:
- Polls backend health every 5 seconds
- Shows connection state
- Shows empire name and game date when available

## Responsive Behavior

**800px - 1200px (Default):**
- Sidebar: 200px fixed
- Content: flex-grow

**1200px+ (Wide):**
- Sidebar: 240px fixed
- Content: max-width 900px, centered

**< 800px (Narrow, if resized):**
- Sidebar collapses to icons only (60px)
- Content fills remaining space

## Animations

- Page transitions: 150ms fade
- Message appear: 200ms slide-up + fade
- Loading dots: 1.2s infinite bounce
- Button hover: 100ms background color
- Status indicator pulse: 2s infinite (for "connecting" state)

## Accessibility

- All interactive elements keyboard accessible
- Focus visible outlines
- aria-labels on icon-only buttons
- Sufficient color contrast (WCAG AA)
- Reduced motion respected
