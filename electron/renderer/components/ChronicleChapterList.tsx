import { motion } from 'framer-motion'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
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
  display_name: string
  ethics?: string[]
  chapter_count: number
  last_date: string
  is_current: boolean
  has_chronicle: boolean
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
  onManageCampaigns?: () => void
  onOpenNarratorPanel?: () => void
  onPublish?: () => void
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
  onManageCampaigns,
  onOpenNarratorPanel,
  onPublish,
  onExport,
  collapsed = false,
  onToggleCollapse,
}: ChronicleChapterListProps) {
  const { t } = useTranslation()
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

      {/* Campaign selector */}
      <div className="p-4">
        <div className="text-xs text-text-secondary uppercase tracking-wider mb-2 font-semibold flex items-center gap-2">
          <span className="text-accent-cyan">◆</span>
          {t('chronicle.sidebar.campaigns')}
          {onToggleCollapse && (
            <button
              type="button"
              onClick={onToggleCollapse}
              className="ml-auto w-5 h-5 flex items-center justify-center rounded text-text-secondary hover:text-accent-cyan transition-colors duration-150"
              title={t('chronicle.sidebar.closeSidebar')}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round">
                <rect x="1.5" y="2.5" width="13" height="11" rx="1.5" />
                <line x1="5.5" y1="2.5" x2="5.5" y2="13.5" />
              </svg>
            </button>
          )}
        </div>
        {saves.length > 1 ? (
          <CampaignPicker
            saves={saves}
            selectedSaveId={selectedSaveId}
            onSelectSave={onSelectSave}
          />
        ) : selectedSave ? (
          <div className="flex items-start gap-2 rounded-md border border-border bg-bg-tertiary/50 p-2.5">
            <span className="mt-0.5 text-base text-accent-teal">◈</span>
            <div className="min-w-0">
              <span className="block break-words text-sm font-medium leading-snug text-text-primary">{selectedSave.display_name}</span>
              <span className="mt-1 block text-[10px] uppercase tracking-wider text-text-muted">
                {selectedSave.is_current
                  ? t('chronicle.sidebar.currentCampaignDate', { date: selectedSave.last_date })
                  : t('chronicle.sidebar.lastPlayed', { date: selectedSave.last_date })}
              </span>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2 p-2.5 bg-bg-tertiary/50 border border-border rounded-md opacity-60">
            <span className="text-text-secondary text-base">◇</span>
            <span className="text-sm font-medium text-text-secondary">{t('chronicle.sidebar.noHistory')}</span>
          </div>
        )}
        {onManageCampaigns && (
          <button
            type="button"
            onClick={onManageCampaigns}
            className="mt-2 w-full rounded border border-border px-3 py-2 text-left text-xs uppercase tracking-wider text-text-secondary transition-colors hover:border-accent-cyan/40 hover:bg-accent-cyan/5 hover:text-accent-cyan"
          >
            {t('chronicle.sidebar.manageCampaigns')}
          </button>
        )}
      </div>

      {/* Chapter list */}
      <nav className="flex-1 overflow-y-auto py-3">
        <h3 className="px-4 py-2 text-xs font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-2">
          <span className="text-accent-cyan/60">◇</span>
          {t('chronicle.sidebar.chapters')}
        </h3>

        {loading && chapters.length === 0 ? (
          <div className="py-4 px-4 text-text-secondary text-sm flex items-center gap-2">
            <span className="w-3 h-3 border border-accent-cyan border-t-transparent rounded-full animate-spin-loader" />
            {t('chronicle.sidebar.loading')}
          </div>
        ) : chapters.length === 0 && !currentEra ? (
          <div className="py-4 px-4">
            <p className="text-text-secondary text-sm mb-2">{t('chronicle.sidebar.noChapters')}</p>
            <p className="text-text-muted text-xs">
              {t('chronicle.sidebar.noChaptersHelp')}
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
                >
                  <motion.button
                    type="button"
                    disabled={isRegenerating}
                    aria-current={isSelected ? 'true' : undefined}
                    className={`mx-2 flex w-[calc(100%-1rem)] items-center gap-2 rounded-md border border-transparent px-4 py-2.5 text-left transition-all duration-150 ${
                      isSelected
                        ? 'border-accent-cyan/30 bg-bg-tertiary'
                        : 'hover:border-border hover:bg-bg-tertiary/50'
                    } ${chapter.context_stale ? 'opacity-70' : ''} ${isThisRegenerating ? 'animate-pulse-text' : ''}`}
                    onClick={() => onSelectChapter(chapter.number)}
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
                    <span className={`flex-1 truncate text-sm ${isSelected ? 'font-medium text-text-primary' : 'text-text-secondary'}`}>
                      {truncateTitle(chapter.title)}
                    </span>
                    <span className="flex items-center gap-1 text-[11px]">
                      {isThisRegenerating ? (
                        <Tooltip content={t('chronicle.sidebar.regenerating')} position="left">
                          <span className="text-accent-yellow animate-spin-loader inline-block">⟳</span>
                        </Tooltip>
                      ) : (
                        <>
                          {chapter.context_stale && (
                            <Tooltip content={t('chronicle.sidebar.staleTooltip')} position="bottom">
                              <span className="text-accent-yellow ">⚠</span>
                            </Tooltip>
                          )}
                          {chapter.is_finalized && (
                            <Tooltip content={t('chronicle.sidebar.finalizedTooltip')} position="left">
                              <span className="text-accent-cyan/60 ">◆</span>
                            </Tooltip>
                          )}
                        </>
                      )}
                    </span>
                  </motion.button>
                </motion.li>
              )
            })}

            {/* Current Era entry */}
            {currentEra && (
              <>
                <motion.li
                  variants={itemVariants}
                >
                  <motion.button
                    type="button"
                    disabled={isRegenerating}
                    aria-current={selectedChapter === null || selectedChapter === 0 ? 'true' : undefined}
                    className={`mx-2 flex w-[calc(100%-1rem)] items-center gap-2 rounded-md border border-transparent px-4 py-2.5 text-left transition-all duration-150 ${
                      selectedChapter === null || selectedChapter === 0
                        ? 'border-accent-teal/30 bg-bg-tertiary'
                        : 'hover:border-border hover:bg-bg-tertiary/50'
                    }`}
                    onClick={() => onSelectChapter(null)}
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
                      {t('chronicle.sidebar.currentEra')}
                    </span>
                  </motion.button>
                </motion.li>
              </>
            )}
          </motion.ul>
        )}
      </nav>

      {/* Story tools */}
      {(onOpenNarratorPanel || onPublish || onExport) && (
        <div className="space-y-2 border-t border-border/70 px-4 py-3">
          {onOpenNarratorPanel && (
          <button
            type="button"
            onClick={onOpenNarratorPanel}
              className="flex w-full items-center gap-2 rounded border border-border bg-bg-tertiary/35 px-3 py-2 text-text-secondary transition-colors hover:border-accent-cyan/45 hover:text-accent-cyan"
          >
            <PersonIcon className="w-4 h-4" />
              <span className="text-xs uppercase tracking-wider">{t('chronicle.sidebar.storyStyle')}</span>
          </button>
          )}
          {(chapters.length > 0 || currentEra) && (onPublish || onExport) && (
            <div className="grid grid-cols-2 gap-2">
              {onPublish && (
                <button
                  type="button"
                  onClick={onPublish}
                  className="flex items-center justify-center gap-2 rounded border border-accent-teal/40 bg-accent-teal/10 px-2 py-2 text-accent-teal transition-colors hover:border-accent-teal/70 hover:bg-accent-teal/15"
                >
                  <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M8 11V3m0 0L5 6m3-3l3 3" />
                    <path d="M3 9v3a1 1 0 001 1h8a1 1 0 001-1V9" />
                  </svg>
                  <span className="text-[10px] uppercase tracking-wider">{t('chronicle.sidebar.publish')}</span>
                </button>
              )}
              {onExport && (
                <button
                  type="button"
                  onClick={onExport}
                  className="flex items-center justify-center gap-2 rounded border border-border px-2 py-2 text-text-secondary transition-colors hover:border-accent-cyan/45 hover:text-accent-cyan"
                >
                  <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M8 2v8m0 0l-3-3m3 3l3-3" />
                    <path d="M2 11v2a1 1 0 001 1h10a1 1 0 001-1v-2" />
                  </svg>
                  <span className="text-[10px] uppercase tracking-wider">{t('chronicle.sidebar.export')}</span>
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Stats footer */}
      <div className="p-4 flex flex-col gap-2">
        <div className="flex justify-between text-xs">
          <span className="text-text-secondary uppercase tracking-wider">{t('chronicle.sidebar.events')}</span>
          <span className="text-text-primary font-mono">{eventCount.toLocaleString()}</span>
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-text-secondary uppercase tracking-wider">{t('chronicle.sidebar.chapters')}</span>
          <span className="text-text-primary font-mono">{chapters.length}</span>
        </div>
        {selectedSave && (
          <div className="flex justify-between text-xs">
            <span className="text-text-secondary uppercase tracking-wider">{t('chronicle.sidebar.latest')}</span>
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
            {t('chronicle.sidebar.pending', { count: pendingChapters })}
          </span>
          <button
            className="w-8 h-8 border border-accent-yellow/50 rounded bg-accent-yellow/10 text-accent-yellow text-sm cursor-pointer flex items-center justify-center transition-all duration-200 hover:bg-accent-yellow/20 hover:shadow-glow-yellow disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={onRefresh}
            disabled={loading}
            title={t('chronicle.sidebar.generateMore')}
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

function CampaignPicker({
  saves,
  selectedSaveId,
  onSelectSave,
}: {
  saves: SaveInfo[]
  selectedSaveId: string | null
  onSelectSave: (saveId: string) => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const selectedSave = saves.find(save => save.save_id === selectedSaveId) || saves[0]

  return (
    <div
      className="relative"
      onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false)
      }}
      onKeyDown={event => {
        if (event.key !== 'Escape') return
        setOpen(false)
        event.currentTarget.querySelector<HTMLElement>('[aria-haspopup="listbox"]')?.focus()
      }}
    >
      <button
        type="button"
        aria-label={t('chronicle.sidebar.chooseCampaign')}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen(previous => !previous)}
        className="flex w-full items-start gap-2 rounded-md border border-border bg-bg-tertiary/70 p-2.5 text-left transition-colors hover:border-accent-cyan/50 focus:border-accent-cyan focus:outline-none focus:shadow-glow-sm"
      >
        <span className="mt-0.5 text-base text-accent-teal">◈</span>
        <span className="min-w-0 flex-1">
          <span className="block break-words text-sm font-medium leading-snug text-text-primary">
            {selectedSave.display_name}
          </span>
          <span className="mt-1 block text-[10px] uppercase tracking-wider text-text-muted">
            {selectedSave.is_current
              ? t('chronicle.sidebar.currentCampaignDate', { date: selectedSave.last_date })
              : t('chronicle.sidebar.lastPlayed', { date: selectedSave.last_date })}
          </span>
        </span>
        <span aria-hidden="true" className={`mt-1 text-xs text-accent-cyan transition-transform ${open ? 'rotate-180' : ''}`}>⌄</span>
      </button>
      {open && <div role="listbox" aria-label={t('chronicle.sidebar.campaigns')} className="absolute left-0 right-0 z-30 mt-2 max-h-64 overflow-y-auto rounded-md border border-accent-cyan/30 bg-bg-primary p-1.5 shadow-xl">
        {saves.map(save => {
          const isSelected = save.save_id === selectedSave.save_id
          return (
            <button
              key={save.save_id}
              type="button"
              role="option"
              aria-selected={isSelected}
              onClick={() => {
                onSelectSave(save.save_id)
                setOpen(false)
              }}
              className={`mb-1 w-full rounded border px-2.5 py-2 text-left transition-colors last:mb-0 ${
                isSelected
                  ? 'border-accent-cyan/35 bg-accent-cyan/10'
                  : 'border-transparent hover:border-border hover:bg-bg-tertiary/70'
              }`}
            >
              <span className="block break-words text-sm font-medium leading-snug text-text-primary">
                {save.display_name}
              </span>
              <span className="mt-1 block text-[10px] uppercase tracking-wider text-text-muted">
                {save.is_current
                  ? t('chronicle.sidebar.currentCampaignDate', { date: save.last_date })
                  : t('chronicle.sidebar.lastPlayed', { date: save.last_date })}
              </span>
            </button>
          )
        })}
      </div>}
    </div>
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
