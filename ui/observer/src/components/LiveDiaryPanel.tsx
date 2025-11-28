import { useMemo, useRef, useEffect, useState } from 'react'
import { AgentProfile, NormalizedDiaryEntry } from '@/lib/bundle'
import { formatTimestamp } from '@/lib/time'
import { MarkdownContent } from './MarkdownContent'
import { useVirtualizer } from '@tanstack/react-virtual'

interface LiveDiaryPanelProps {
  diaries: Record<string, NormalizedDiaryEntry[]>
  agents: Record<string, AgentProfile>
  maxEntries?: number
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

const avatarPalette = [
  'border-emerald-500/50 bg-emerald-500/10 text-emerald-100',
  'border-sky-500/50 bg-sky-500/10 text-sky-100',
  'border-purple-500/50 bg-purple-500/10 text-purple-100',
  'border-amber-500/50 bg-amber-500/10 text-amber-100',
  'border-rose-500/50 bg-rose-500/10 text-rose-100',
]

export const LiveDiaryPanel = ({
  diaries,
  agents,
  maxEntries = 50,
}: LiveDiaryPanelProps) => {
  const [autoScroll, setAutoScroll] = useState(true)
  const [selectedAgent, setSelectedAgent] = useState<string | 'all'>('all')
  const parentRef = useRef<HTMLDivElement | null>(null)

  const agentOrder = useMemo(() => Object.keys(agents).sort(), [agents])

  const entries = useMemo(() => {
    const allEntries: DiaryEntrySummary[] = Object.entries(diaries).flatMap(
      ([agentId, agentEntries]) =>
        agentEntries.map((entry, index) => ({
          id: `diary-${agentId}-${entry.createdAtMs}-${index}`,
          tsMs: entry.createdAtMs,
          agentId,
          text: entry.text,
          tags: entry.tags ?? [],
          lifeIndex: entry.life_index,
          entryIndex: entry.entry_index,
        }))
    )

    const filtered =
      selectedAgent === 'all'
        ? allEntries
        : allEntries.filter((e) => e.agentId === selectedAgent)

    return filtered.sort((a, b) => b.tsMs - a.tsMs).slice(0, maxEntries)
  }, [diaries, selectedAgent, maxEntries])

  const rowVirtualizer = useVirtualizer({
    count: entries.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 160,
    overscan: 6,
    getItemKey: (index) => entries[index]?.id ?? index,
  })

  const virtualItems = rowVirtualizer.getVirtualItems()
  const totalHeight = rowVirtualizer.getTotalSize()

  // Auto-scroll to top (newest entries) when new entries arrive
  useEffect(() => {
    if (autoScroll && entries.length > 0 && parentRef.current) {
      parentRef.current.scrollTop = 0
    }
  }, [entries.length, autoScroll])

  return (
    <aside className="space-y-4 lg:sticky lg:top-6">
      <section className="rounded-3xl border border-white/5 bg-panel/60 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
              Live Diaries
            </p>
            <p className="text-sm text-slate-300">
              {entries.length} entr{entries.length === 1 ? 'y' : 'ies'}
              {selectedAgent !== 'all' && (
                <span className="ml-1 text-slate-500">
                  from {agents[selectedAgent]?.display_name ?? selectedAgent}
                </span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={selectedAgent}
              onChange={(e) => setSelectedAgent(e.target.value)}
              className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 focus:border-accent focus:outline-none"
            >
              <option value="all">All Agents</option>
              {agentOrder.map((agentId) => (
                <option key={agentId} value={agentId}>
                  {agents[agentId]?.display_name ?? agentId}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div
          ref={parentRef}
          className="mt-4 max-h-[70vh] overflow-y-auto pr-1"
        >
          {entries.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-4 text-center text-xs text-slate-500">
              No diary entries yet. Agents will write reflections as they process ticks.
            </div>
          ) : (
            <ul className="relative" style={{ height: totalHeight }}>
              {virtualItems.map((item) => {
                const entry = entries[item.index]
                const profile = agents[entry.agentId]
                const name = profile?.display_name ?? entry.agentId
                const toneIndex = agentOrder.indexOf(entry.agentId)
                const tone =
                  avatarPalette[
                    toneIndex === -1 ? 0 : toneIndex % avatarPalette.length
                  ]
                const initials = name
                  .split(/[\s_-]+/)
                  .slice(0, 2)
                  .map((w) => w.charAt(0).toUpperCase())
                  .join('')

                const label = entry.entryIndex
                  ? `${name} · Entry #${entry.entryIndex}`
                  : name

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
                    <div className="rounded-2xl border border-white/5 bg-white/5 p-3 text-slate-200">
                      <div className="flex items-start gap-3">
                        <span
                          className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border text-[10px] font-semibold uppercase tracking-wide ${tone}`}
                        >
                          {initials}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
                            <span className="font-semibold text-slate-200">
                              {label}
                            </span>
                            <span>{formatTimestamp(entry.tsMs)}</span>
                          </div>
                          <div className="mt-2">
                            <MarkdownContent content={entry.text.trim()} />
                          </div>
                          {(entry.lifeIndex !== undefined ||
                            entry.tags.length > 0) && (
                            <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-wide text-slate-500">
                              {entry.lifeIndex !== undefined && (
                                <span className="rounded-full bg-white/5 px-2 py-0.5">
                                  Life {entry.lifeIndex}
                                </span>
                              )}
                              {entry.tags.slice(0, 4).map((tag) => (
                                <span
                                  key={`${entry.id}-${tag}`}
                                  className="rounded-full bg-white/5 px-2 py-0.5"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        {entries.length > 0 && (
          <div className="mt-3 flex justify-center">
            <button
              type="button"
              onClick={() => setAutoScroll(!autoScroll)}
              className={`rounded-lg border px-3 py-1.5 text-xs transition ${
                autoScroll
                  ? 'border-emerald-500/50 bg-emerald-500/20 text-emerald-300'
                  : 'border-white/10 bg-white/5 text-slate-400 hover:bg-white/10'
              }`}
            >
              {autoScroll ? 'Auto-scroll to new' : 'Manual scroll'}
            </button>
          </div>
        )}
      </section>
    </aside>
  )
}
