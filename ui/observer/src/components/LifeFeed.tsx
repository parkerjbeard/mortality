import { useMemo } from 'react'
import { PlaybackControls } from '@/hooks/usePlayback'
import {
  NormalizedBundle,
  NormalizedDiaryEntry,
  eventAgentId,
} from '@/lib/bundle'
import { formatCountdown, formatTimestamp } from '@/lib/time'
import clsx from 'clsx'

type InsightType = 'diary' | 'spawn' | 'death' | 'respawn'

interface InsightEntry {
  id: string
  tsMs: number
  agentId: string
  type: InsightType
  label: string
  detail?: string
  lifeIndex?: number
  tickMsLeft?: number
}

interface LifeFeedProps {
  bundle: NormalizedBundle
  playback: PlaybackControls
  onJump: (tsMs: number) => void
  limit?: number
}

export const LifeFeed = ({
  bundle,
  playback,
  onJump,
  limit = 28,
}: LifeFeedProps) => {
  const entries = useMemo(
    () => collectInsights(bundle, playback.playheadMs, limit),
    [bundle, playback.playheadMs, limit],
  )
  const playheadLabel = formatTimestamp(playback.playheadMs)

  return (
    <section className="rounded-3xl border border-white/5 bg-panel/40 p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
            Life feed
          </p>
          <p className="text-sm text-slate-300">
            Key insights until {playheadLabel}
          </p>
        </div>
        <span className="text-xs text-slate-500">
          Showing {entries.length} / {limit}
        </span>
      </div>
      <ul className="mt-4 space-y-2">
        {entries.map((entry) => {
          const agent = bundle.agents[entry.agentId]
          const agentName = agent?.display_name ?? entry.agentId
          const tone = toneByType[entry.type]
          return (
            <li key={entry.id}>
              <button
                type="button"
                className={clsx(
                  'w-full rounded-2xl border px-3 py-2 text-left text-slate-200 transition',
                  tone,
                  'hover:border-white/40 hover:bg-white/10',
                )}
                onClick={() => onJump(entry.tsMs)}
              >
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>{agentName}</span>
                  <span>{formatTimestamp(entry.tsMs)}</span>
                </div>
                <p className="mt-1 text-sm font-medium text-white">
                  {entry.label}
                </p>
                {entry.detail && (
                  <p className="mt-1 line-clamp-3 text-sm text-slate-300">
                    {entry.detail}
                  </p>
                )}
                <div className="mt-2 flex flex-wrap gap-2 text-[11px] uppercase tracking-wide text-slate-500">
                  {entry.lifeIndex !== undefined && (
                    <span>Life {entry.lifeIndex}</span>
                  )}
                  {entry.tickMsLeft !== undefined && (
                    <span>{formatCountdown(entry.tickMsLeft)}</span>
                  )}
                  <span>{entry.type}</span>
                </div>
              </button>
            </li>
          )
        })}
        {entries.length === 0 && (
          <li className="rounded-2xl border border-white/5 bg-white/5 p-3 text-sm text-slate-500">
            Advance the playhead or restart playback to surface insights.
          </li>
        )}
      </ul>
    </section>
  )
}

const toneByType: Record<InsightType, string> = {
  diary: 'border-white/10 bg-white/5',
  spawn: 'border-white/5 bg-emerald-500/5 text-emerald-200',
  death: 'border-danger/20 bg-danger/5 text-danger',
  respawn: 'border-warning/20 bg-warning/5 text-warning',
}

const collectInsights = (
  bundle: NormalizedBundle,
  playheadMs: number,
  limit: number,
): InsightEntry[] => {
  const diaries = Object.entries(bundle.diaries).flatMap(([agentId, list]) => {
    return list
      .filter((entry) => entry.createdAtMs <= playheadMs)
      .map((entry) => diaryToInsight(agentId, entry))
  })

  const lifecycleEvents = bundle.events
    .filter(
      (event) => event.tsMs <= playheadMs && lifecycleKinds.has(event.event),
    )
    .map((event): InsightEntry | null => {
      const agentId = eventAgentId(event)
      if (!agentId) return null
      const type = mapLifecycleType(event.event)
      return {
        id: `event-${event.seq}`,
        tsMs: event.tsMs,
        agentId,
        type,
        label: labelForLifecycle(type, event.payload.life_index),
        lifeIndex:
          typeof event.payload.life_index === 'number'
            ? event.payload.life_index
            : undefined,
      }
    })
    .filter((entry): entry is InsightEntry => entry !== null)

  return [...diaries, ...lifecycleEvents]
    .sort((a, b) => b.tsMs - a.tsMs)
    .slice(0, limit)
}

const lifecycleKinds = new Set([
  'agent.spawned',
  'agent.death',
  'agent.respawn',
])

const mapLifecycleType = (event: string): InsightType => {
  switch (event) {
    case 'agent.spawned':
      return 'spawn'
    case 'agent.death':
      return 'death'
    case 'agent.respawn':
      return 'respawn'
    default:
      return 'diary'
  }
}

const diaryToInsight = (
  agentId: string,
  entry: NormalizedDiaryEntry,
): InsightEntry => ({
  id: `diary-${agentId}-${entry.createdAtMs}`,
  tsMs: entry.createdAtMs,
  agentId,
  type: 'diary',
  label: entry.tags?.length ? entry.tags.join(' · ') : 'Diary insight',
  detail: entry.text,
  lifeIndex: entry.life_index,
  tickMsLeft: entry.tick_ms_left,
})

const labelForLifecycle = (type: InsightType, lifeIndex?: number) => {
  switch (type) {
    case 'spawn':
      return 'Spawned into simulation'
    case 'death':
      return 'Timer expired'
    case 'respawn':
      return `Respawned${typeof lifeIndex === 'number' ? ` (life ${lifeIndex})` : ''}`
    default:
      return 'Lifecycle update'
  }
}
