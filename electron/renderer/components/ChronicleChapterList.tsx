import { motion } from 'framer-motion'
import { ChronicleChapter, CurrentEra } from '../hooks/useBackend'
import Tooltip from './Tooltip'
import PersonIcon from './PersonIcon'

// Staggered list animation
const listVariants = {
  animate: {
    transition: {
      staggerChildren: 0.03,
    },
  },
}

const itemVariants = {
  initial: { opacity: 0, x: -12 },
  animate: { opacity: 1, x: 0 },
}

interface SaveInfo {
  save_id: string
  empire_name: string
  ethics?: string[]
  chapter_count: number
  last_date: string
}

interface ChronicleChapterListProps {
  saves: SaveInfo[]
  selectedSaveId: string | null
  onSelectSave: (saveId: string) => void
  chapters: ChronicleChapter[]
  currentEra: CurrentEra | null
  selectedChapter: number | null
  onSelectChapter: (chapterNumber: number | null) => void
  pendingChapters: number
  eventCount: number
  loading: boolean
  regeneratingChapter: number | null
  onRefresh: () => void
  onOpenNarratorPanel?: () => void
  onExport?: () => void
  collapsed?: boolean
  onToggleCollapse?: () => void
}

/**
 * ChronicleChapterList - Sidebar navigation for the Galactic Archives
 */
function ChronicleChapterList({
  saves,
  selectedSaveId,
  onSelectSave,
  chapters,
  currentEra,
  selectedChapter,
  onSelectChapter,
  pendingChapters,
  eventCount,
  loading,
  regeneratingChapter,
  onRefresh,
  onOpenNarratorPanel,
  onExport,
  collapsed = false,
  onToggleCollapse,
}: ChronicleChapterListProps) {
  const isRegenerating = regeneratingChapter !== null
  const selectedSave = saves.find(s => s.save_id === selectedSaveId)

  return (
    <motion.aside
      className="flex-shrink-0 flex flex-col relative overflow-hidden"
      animate={{ width: collapsed ? 0 : 280 }}
      transition={{ duration: 0.25, ease: 'easeInOut' }}
    >
      {/* Right border - fades at top and bottom */}
      <div className="absolute right-0 top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-border to-transparent" />
      {/* Subtle cyan glow overlay */}
      <div className="absolute right-0 top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-accent-cyan/20 to-transparent" />

      {/* Empire selector */}
      <div className="p-4">
        <div className="text-xs text-text-secondary uppercase tracking-wider mb-2 font-semibold flex items-center gap-2">
          <span className="text-accent-cyan">◆</span>
          Empire Archives
          {onToggleCollapse && (
            <button
              type="button"
              onClick={onToggleCollapse}
              className="ml-auto w-5 h-5 flex items-center justify-center rounded text-text-secondary hover:text-accent-cyan transition-colors duration-150"
              title="Close sidebar"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round">
                <rect x="1.5" y="2.5" width="13" height="11" rx="1.5" />
                <line x1="5.5" y1="2.5" x2="5.5" y2="13.5" />
              </svg>
            </button>
          )}
        </div>
        {saves.length > 1 ? (
          <select
            value={selectedSaveId || ''}
            onChange={(e) => onSelectSave(e.target.value)}
            className="w-full p-2.5 bg-bg-tertiary border border-border rounded-md text-text-primary text-sm font-medium cursor-pointer transition-colors duration-200 hover:border-accent-cyan/50 focus:border-accent-cyan focus:outline-none focus:shadow-glow-sm"
          >
            {saves.map(save => (
              <option key={save.save_id} value={save.save_id}>
                {save.empire_name}
              </option>
            ))}
          </select>
        ) : selectedSave ? (
          <div className="flex items-center gap-2 p-2.5 bg-bg-tertiary/50 border border-border rounded-md">
            <span className="text-accent-teal text-base">◈</span>
            <span className="text-sm font-medium text-text-primary truncate">{selectedSave.empire_name}</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 p-2.5 bg-bg-tertiary/50 border border-border rounded-md opacity-60">
            <span className="text-text-secondary text-base">◇</span>
            <span className="text-sm font-medium text-text-secondary">No game history yet</span>
          </div>
        )}
      </div>

      {/* Chapter list */}
      <nav className="flex-1 overflow-y-auto py-3">
        <h3 className="px-4 py-2 text-xs font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-2">
          <span className="text-accent-cyan/60">◇</span>
          Chapters
        </h3>

        {loading && chapters.length === 0 ? (
          <div className="py-4 px-4 text-text-secondary text-sm flex items-center gap-2">
            <span className="w-3 h-3 border border-accent-cyan border-t-transparent rounded-full animate-spin-loader" />
            Loading...
          </div>
        ) : chapters.length === 0 && !currentEra ? (
          <div className="py-4 px-4">
            <p className="text-text-secondary text-sm mb-2">No chapters yet</p>
            <p className="text-text-muted text-xs">
              Play around 5 years with enough events, or hit a major event, to generate your first chapter.
            </p>
          </div>
        ) : (
          <motion.ul
            className={`list-none m-0 p-0 ${isRegenerating ? 'opacity-60 pointer-events-none' : ''}`}
            variants={listVariants}
            initial="initial"
            animate="animate"
          >
            {chapters.map(chapter => {
              const isThisRegenerating = regeneratingChapter === chapter.number
              const isSelected = selectedChapter === chapter.number
              return (
                <motion.li
                  key={chapter.number}
                  variants={itemVariants}
                  className={`flex items-center gap-2 px-4 py-2.5 mx-2 rounded-md cursor-pointer transition-all duration-150 border border-transparent ${
                    isSelected
                      ? 'bg-bg-tertiary border-accent-cyan/30'
                      : 'hover:bg-bg-tertiary/50 hover:border-border'
                  } ${chapter.context_stale ? 'opacity-70' : ''} ${isThisRegenerating ? 'animate-pulse-text' : ''}`}
                  onClick={() => !isRegenerating && onSelectChapter(chapter.number)}
                  whileHover={{ x: 4 }}
                  whileTap={{ scale: 0.98 }}
                  transition={{ duration: 0.1 }}
                >
                  <span className={`w-8 text-center text-xs font-mono ${isSelected ? 'text-accent-cyan' : 'text-text-secondary'}`}>
                    {isThisRegenerating ? (
                      <span className="inline-block w-3 h-3 border border-accent-yellow border-t-transparent rounded-full animate-spin-loader" />
                    ) : (
                      toRoman(chapter.number)
                    )}
                  </span>
                  <span className={`flex-1 text-sm truncate ${isSelected ? 'text-text-primary font-medium' : 'text-text-secondary'}`}>
                    {truncateTitle(chapter.title)}
                  </span>
                  <span className="flex items-center gap-1 text-[11px]">
                    {isThisRegenerating ? (
                      <Tooltip content="Regenerating chapter..." position="left">
                        <span className="text-accent-yellow animate-spin-loader inline-block">⟳</span>
                      </Tooltip>
                    ) : (
                      <>
                        {chapter.context_stale && (
                          <Tooltip content="Earlier chapter was regenerated — context may be outdated" position="bottom">
                            <span className="text-accent-yellow ">⚠</span>
                          </Tooltip>
                        )}
                        {chapter.is_finalized && (
                          <Tooltip content="Finalized chapter" position="left">
                            <span className="text-accent-cyan/60 ">◆</span>
                          </Tooltip>
                        )}
                      </>
                    )}
                  </span>
                </motion.li>
              )
            })}

            {/* Current Era entry */}
            {currentEra && (
              <>
                <motion.li
                  variants={itemVariants}
                  className={`flex items-center gap-2 px-4 py-2.5 mx-2 rounded-md cursor-pointer transition-all duration-150 border border-transparent ${
                    selectedChapter === null || selectedChapter === 0
                      ? 'bg-bg-tertiary border-accent-teal/30'
                      : 'hover:bg-bg-tertiary/50 hover:border-border'
                  }`}
                  onClick={() => !isRegenerating && onSelectChapter(null)}
                  whileHover={{ x: 4 }}
                  whileTap={{ scale: 0.98 }}
                  transition={{ duration: 0.1 }}
                >
                  <span className="w-8 text-center text-accent-yellow text-sm">⏳</span>
                  <span className={`flex-1 text-sm ${
                    selectedChapter === null || selectedChapter === 0
                      ? 'text-text-primary font-medium'
                      : 'text-text-secondary'
                  }`}>
                    Current Era
                  </span>
                </motion.li>
              </>
            )}
          </motion.ul>
        )}
      </nav>

      {/* Narrator button */}
      {onOpenNarratorPanel && (
        <div className="px-4 pb-2">
          <button
            type="button"
            onClick={onOpenNarratorPanel}
            className="flex items-center gap-2 w-full px-3 py-2 border border-accent-cyan/30 bg-accent-cyan/5 rounded text-accent-cyan/70 hover:text-accent-cyan hover:border-accent-cyan/60 hover:bg-accent-cyan/10 hover:shadow-glow-sm transition-all duration-200 relative group"
          >
            <div className="absolute top-0 left-0 w-1.5 h-1.5 border-l border-t border-accent-cyan/50 group-hover:border-accent-cyan/80 transition-colors" />
            <div className="absolute top-0 right-0 w-1.5 h-1.5 border-r border-t border-accent-cyan/50 group-hover:border-accent-cyan/80 transition-colors" />
            <div className="absolute bottom-0 left-0 w-1.5 h-1.5 border-l border-b border-accent-cyan/50 group-hover:border-accent-cyan/80 transition-colors" />
            <div className="absolute bottom-0 right-0 w-1.5 h-1.5 border-r border-b border-accent-cyan/50 group-hover:border-accent-cyan/80 transition-colors" />
            <PersonIcon className="w-4 h-4" />
            <span className="text-xs uppercase tracking-wider font-semibold">Narrator</span>
          </button>
        </div>
      )}

      {/* Export button */}
      {onExport && (chapters.length > 0 || currentEra) && (
        <div className="px-4 pb-2">
          <button
            type="button"
            onClick={onExport}
            className="flex items-center gap-2 w-full px-3 py-2 border border-accent-cyan/30 bg-accent-cyan/5 rounded text-accent-cyan/70 hover:text-accent-cyan hover:border-accent-cyan/60 hover:bg-accent-cyan/10 hover:shadow-glow-sm transition-all duration-200 relative group"
          >
            <div className="absolute top-0 left-0 w-1.5 h-1.5 border-l border-t border-accent-cyan/50 group-hover:border-accent-cyan/80 transition-colors" />
            <div className="absolute top-0 right-0 w-1.5 h-1.5 border-r border-t border-accent-cyan/50 group-hover:border-accent-cyan/80 transition-colors" />
            <div className="absolute bottom-0 left-0 w-1.5 h-1.5 border-l border-b border-accent-cyan/50 group-hover:border-accent-cyan/80 transition-colors" />
            <div className="absolute bottom-0 right-0 w-1.5 h-1.5 border-r border-b border-accent-cyan/50 group-hover:border-accent-cyan/80 transition-colors" />
            <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M8 2v8m0 0l-3-3m3 3l3-3" />
              <path d="M2 11v2a1 1 0 001 1h10a1 1 0 001-1v-2" />
            </svg>
            <span className="text-xs uppercase tracking-wider font-semibold">Export</span>
          </button>
        </div>
      )}

      {/* Stats footer */}
      <div className="p-4 flex flex-col gap-2">
        <div className="flex justify-between text-xs">
          <span className="text-text-secondary uppercase tracking-wider">Events</span>
          <span className="text-text-primary font-mono">{eventCount.toLocaleString()}</span>
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-text-secondary uppercase tracking-wider">Chapters</span>
          <span className="text-text-primary font-mono">{chapters.length}</span>
        </div>
        {selectedSave && (
          <div className="flex justify-between text-xs">
            <span className="text-text-secondary uppercase tracking-wider">Latest</span>
            <span className="text-accent-cyan font-mono">{selectedSave.last_date}</span>
          </div>
        )}
      </div>

      {/* Pending chapters notification */}
      {pendingChapters > 0 && (
        <div className="p-4 border-t border-border flex items-center gap-2 bg-accent-yellow/5">
          <span className="bg-accent-yellow text-bg-primary text-xs font-semibold py-0.5 px-2 rounded flex items-center gap-1">
            <span>⚡</span>
            {pendingChapters}
          </span>
          <span className="flex-1 text-xs text-text-secondary">
            {pendingChapters === 1 ? 'chapter' : 'chapters'} pending
          </span>
          <button
            className="w-8 h-8 border border-accent-yellow/50 rounded bg-accent-yellow/10 text-accent-yellow text-sm cursor-pointer flex items-center justify-center transition-all duration-200 hover:bg-accent-yellow/20 hover:shadow-glow-yellow disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={onRefresh}
            disabled={loading}
            title="Generate more chapters"
          >
            {loading ? (
              <span className="w-3 h-3 border border-accent-yellow border-t-transparent rounded-full animate-spin-loader" />
            ) : (
              '↻'
            )}
          </button>
        </div>
      )}
    </motion.aside>
  )
}

/**
 * Convert number to Roman numerals
 */
function toRoman(num: number): string {
  const romanNumerals: [number, string][] = [
    [10, 'X'],
    [9, 'IX'],
    [5, 'V'],
    [4, 'IV'],
    [1, 'I'],
  ]

  let result = ''
  let remaining = num

  for (const [value, numeral] of romanNumerals) {
    while (remaining >= value) {
      result += numeral
      remaining -= value
    }
  }

  return result
}

/**
 * Truncate long chapter titles for sidebar
 */
function truncateTitle(title: string, maxLength = 20): string {
  // Remove "Chapter X: " prefix if present
  const cleaned = title.replace(/^Chapter\s+\w+:\s*/i, '')

  if (cleaned.length <= maxLength) return cleaned
  return cleaned.slice(0, maxLength - 1) + '…'
}

export default ChronicleChapterList
