import { ChronicleChapter, CurrentEra } from '../hooks/useBackend'

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
  onRefresh: () => void
}

/**
 * ChronicleChapterList - Left sidebar for chronicle navigation
 *
 * Displays:
 * - Game/save selector dropdown
 * - Chapter list with finalized/current indicators
 * - Stats footer
 * - Pending chapters notification
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
  onRefresh,
}: ChronicleChapterListProps) {
  const selectedSave = saves.find(s => s.save_id === selectedSaveId)

  return (
    <aside className="chronicle-sidebar">
      {/* Game selector */}
      <div className="chronicle-game-selector">
        {saves.length > 1 ? (
          <select
            value={selectedSaveId || ''}
            onChange={(e) => onSelectSave(e.target.value)}
            className="game-dropdown"
          >
            {saves.map(save => (
              <option key={save.save_id} value={save.save_id}>
                {save.empire_name}
              </option>
            ))}
          </select>
        ) : selectedSave ? (
          <div className="game-single">
            <span className="game-icon">🎮</span>
            <span className="game-name">{selectedSave.empire_name}</span>
          </div>
        ) : (
          <div className="game-none">
            <span className="game-icon">🎮</span>
            <span className="game-name">No save loaded</span>
          </div>
        )}
      </div>

      <div className="chronicle-divider" />

      {/* Chapter list */}
      <nav className="chronicle-chapters">
        <h3 className="chapters-header">CHAPTERS</h3>

        {loading && chapters.length === 0 ? (
          <div className="chapters-loading">Loading...</div>
        ) : chapters.length === 0 && !currentEra ? (
          <div className="chapters-empty">
            <p>No chapters yet</p>
            <p className="chapters-empty-hint">
              Play 50+ years or reach a major event to generate your first chapter.
            </p>
          </div>
        ) : (
          <ul className="chapters-list">
            {chapters.map(chapter => (
              <li
                key={chapter.number}
                className={`chapter-item ${selectedChapter === chapter.number ? 'selected' : ''} ${chapter.context_stale ? 'stale' : ''}`}
                onClick={() => onSelectChapter(chapter.number)}
              >
                <span className="chapter-number">{toRoman(chapter.number)}</span>
                <span className="chapter-title">{truncateTitle(chapter.title)}</span>
                <span className="chapter-status">
                  {chapter.context_stale && <span className="status-stale" title="Context may be stale">⚠️</span>}
                  {chapter.is_finalized && <span className="status-finalized" title="Finalized">🔒</span>}
                </span>
              </li>
            ))}

            {/* Current Era entry */}
            {currentEra && (
              <>
                <li className="chapter-divider" />
                <li
                  className={`chapter-item current-era ${selectedChapter === null || selectedChapter === 0 ? 'selected' : ''}`}
                  onClick={() => onSelectChapter(null)}
                >
                  <span className="chapter-number">⏳</span>
                  <span className="chapter-title">Current Era</span>
                </li>
              </>
            )}
          </ul>
        )}
      </nav>

      <div className="chronicle-divider" />

      {/* Stats footer */}
      <div className="chronicle-stats">
        <div className="stat-row">
          <span className="stat-label">Events</span>
          <span className="stat-value">{eventCount.toLocaleString()}</span>
        </div>
        <div className="stat-row">
          <span className="stat-label">Chapters</span>
          <span className="stat-value">{chapters.length}</span>
        </div>
        {selectedSave && (
          <div className="stat-row">
            <span className="stat-label">Latest</span>
            <span className="stat-value">{selectedSave.last_date}</span>
          </div>
        )}
      </div>

      {/* Pending chapters notification */}
      {pendingChapters > 0 && (
        <div className="chronicle-pending">
          <span className="pending-badge">⚡ {pendingChapters}</span>
          <span className="pending-text">
            {pendingChapters === 1 ? 'chapter' : 'chapters'} pending
          </span>
          <button
            className="pending-refresh"
            onClick={onRefresh}
            disabled={loading}
            title="Generate more chapters"
          >
            {loading ? '...' : '↻'}
          </button>
        </div>
      )}
    </aside>
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
function truncateTitle(title: string, maxLength = 18): string {
  // Remove "Chapter X: " prefix if present
  const cleaned = title.replace(/^Chapter\s+\w+:\s*/i, '')

  if (cleaned.length <= maxLength) return cleaned
  return cleaned.slice(0, maxLength - 1) + '…'
}

export default ChronicleChapterList
