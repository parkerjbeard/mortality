import { useMemo, useRef } from 'react'
import { NormalizedBundle } from '@/lib/bundle'
import { PlaybackControls } from '@/hooks/usePlayback'
import { formatTimestamp } from '@/lib/time'
import { MarkdownContent } from './MarkdownContent'
import { useVirtualizer } from '@tanstack/react-virtual'

interface DiaryPanelProps {
  bundle: NormalizedBundle
  playback: PlaybackControls
  onJump: (tsMs: number) => void
  limit?: number
}

interface DiaryEntrySummary {
  id: string
  tsMs: number
  agentId: string
  text: string
  tags: string[]
  lifeIndex?: number
  entryIndex?: number
}

export const DiaryPanel = ({
  bundle,
  playback,
  onJump,
  limit = 32,
}: DiaryPanelProps) => {
  const entries = useMemo(
    () => collectDiaryEntries(bundle, playback.playheadMs, limit),
    [bundle, playback.playheadMs, limit],
  )

  const parentRef = useRef<HTMLDivElement | null>(null)
  const rowVirtualizer = useVirtualizer({
    count: entries.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 180,
    overscan: 6,
    getItemKey: (index) => entries[index]?.id ?? index,
  })
  const virtualItems = rowVirtualizer.getVirtualItems()
  const totalHeight = rowVirtualizer.getTotalSize()

  return (
    <aside className="space-y-4 lg:sticky lg:top-6">
      <section className="rounded-3xl border border-white/5 bg-panel/60 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
              Diary monitor
            </p>
            <p className="text-sm text-slate-300">
              Reflections captured until{' '}
              <span className="text-white">
                {formatTimestamp(playback.playheadMs)}
              </span>
            </p>
          </div>
          <span className="text-xs text-slate-500">{entries.length} shown</span>
        </div>
        <div
          ref={parentRef}
          className="mt-4 max-h-[70vh] overflow-y-auto pr-1"
        >
          {entries.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-4 text-center text-xs text-slate-500">
              Diaries have not been written yet at this timestamp.
            </div>
          ) : (
            <ul className="relative" style={{ height: totalHeight }}>
              {virtualItems.map((item) => {
                const entry = entries[item.index]
                const profile = bundle.agents[entry.agentId]
                const name = profile?.display_name ?? entry.agentId
                const label = entry.entryIndex
                  ? `${name} · Entry #${entry.entryIndex}`
                  : name
                const detail = entry.text.trim()
                return (
                  <li
                    key={entry.id}
                    className="absolute w-full pb-3"
                    style={{
                      top: 0,
                      left: 0,
                      transform: `translateY(${item.start}px)`,
                    }}
                    ref={rowVirtualizer.measureElement}
                  >
                    <button
                      type="button"
                      onClick={() => onJump(entry.tsMs)}
                      className="block w-full rounded-2xl border border-white/5 bg-white/5 p-3 text-left text-slate-200 transition hover:border-white/30 hover:bg-white/10"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
                        <span className="font-semibold text-slate-200">
                          {label}
                        </span>
                        <span>{formatTimestamp(entry.tsMs)}</span>
                      </div>
                      <div className="mt-2">
                        <MarkdownContent content={detail} />
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-wide text-slate-500">
                        {entry.lifeIndex !== undefined && (
                          <span className="rounded-full bg-white/5 px-2 py-0.5">
                            Life {entry.lifeIndex}
                          </span>
                        )}
                        {entry.tags.map((tag) => (
                          <span
                            key={`${entry.id}-${tag}`}
                            className="rounded-full bg-white/5 px-2 py-0.5"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </section>
    </aside>
  )
}

const collectDiaryEntries = (
  bundle: NormalizedBundle,
  playheadMs: number,
  limit: number,
): DiaryEntrySummary[] => {
  return Object.entries(bundle.diaries)
    .flatMap(([agentId, entries]) =>
      entries
        .filter((entry) => entry.createdAtMs <= playheadMs)
        .map((entry) => ({
          id: `diary-${agentId}-${entry.createdAtMs}`,
          tsMs: entry.createdAtMs,
          agentId,
          text: entry.text,
          tags: Array.isArray(entry.tags) ? entry.tags.slice(0, 4) : [],
          lifeIndex:
            typeof entry.life_index === 'number' ? entry.life_index : undefined,
          entryIndex:
            typeof entry.entry_index === 'number' && entry.entry_index > 0
              ? entry.entry_index
              : undefined,
        })),
    )
    .sort((a, b) => b.tsMs - a.tsMs)
    .slice(0, limit)
}
