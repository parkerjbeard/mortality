import { useMemo } from 'react'
import { NormalizedBundle } from '@/lib/bundle'
import { PlaybackControls } from '@/hooks/usePlayback'
import { formatCountdown, formatTimestamp } from '@/lib/time'

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
  tickMsLeft?: number
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
        <ul className="mt-4 max-h-[70vh] space-y-3 overflow-y-auto pr-1">
          {entries.map((entry) => {
            const profile = bundle.agents[entry.agentId]
            const name = profile?.display_name ?? entry.agentId
            const detail = entry.text.trim()
            return (
              <li key={entry.id}>
                <button
                  type="button"
                  onClick={() => onJump(entry.tsMs)}
                  className="block w-full rounded-2xl border border-white/5 bg-white/5 p-3 text-left text-slate-200 transition hover:border-white/30 hover:bg-white/10"
                >
                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <span className="font-semibold text-slate-200">{name}</span>
                    <span>{formatTimestamp(entry.tsMs)}</span>
                  </div>
                  <p className="mt-2 text-sm text-white whitespace-pre-wrap">
                    {detail}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-wide text-slate-500">
                    {entry.lifeIndex !== undefined && (
                      <span className="rounded-full bg-white/5 px-2 py-0.5">
                        Life {entry.lifeIndex}
                      </span>
                    )}
                    {entry.tickMsLeft !== undefined && (
                      <span className="rounded-full bg-white/5 px-2 py-0.5">
                        {formatCountdown(entry.tickMsLeft)}
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
          {entries.length === 0 && (
            <li className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-4 text-center text-xs text-slate-500">
              Diaries have not been written yet at this timestamp.
            </li>
          )}
        </ul>
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
          tickMsLeft:
            typeof entry.tick_ms_left === 'number'
              ? entry.tick_ms_left
              : undefined,
        })),
    )
    .sort((a, b) => b.tsMs - a.tsMs)
    .slice(0, limit)
}
