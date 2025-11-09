import { NormalizedBundle, NormalizedDiaryEntry, NormalizedEvent } from '@/lib/bundle'
import { AgentSnapshot } from '@/lib/derive'
import { formatCountdown } from '@/lib/time'
import clsx from 'clsx'

interface TimelineLaneProps {
  bundle: NormalizedBundle
  agentId: string
  snapshot?: AgentSnapshot
  onSelectDiary: (agentId: string, entry: NormalizedDiaryEntry) => void
  selectedKey?: string | null
  highlightedKeys: Set<string>
}

export const TimelineLane = ({
  bundle,
  agentId,
  snapshot,
  onSelectDiary,
  selectedKey,
  highlightedKeys,
}: TimelineLaneProps) => {
  const diaries = bundle.diaries[agentId] ?? []
  const events = bundle.eventsByAgent[agentId] ?? []
  const ticks = events.filter((event) => event.event === 'timer.tick').slice(0, 40)
  const deathEvents = events.filter((event) => event.event === 'agent.death')
  const respawns = events.filter((event) => event.event === 'agent.respawn')
  const timeline = bundle.timeline

  const percent = (ts: number) => `${(((ts - timeline.startMs) / timeline.durationMs) * 100).toFixed(3)}%`

  return (
    <div className="rounded-3xl border border-white/5 bg-panel/20 p-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">{bundle.agents[agentId].archetype}</p>
          <h4 className="text-lg font-semibold text-white">{bundle.agents[agentId].display_name}</h4>
        </div>
        {snapshot && (
          <div className="text-right text-xs text-slate-400">
            <p>Status: {snapshot.status}</p>
            <p>Countdown: {formatCountdown(snapshot.msLeft)}</p>
          </div>
        )}
      </div>
      <div className="relative mt-4 h-28">
        <div className="absolute inset-y-1/2 left-0 right-0 h-px bg-white/10" />
        {ticks.map((tick) => (
          <div
            key={tick.seq}
            className="absolute top-1/2 h-4 w-[2px] -translate-y-1/2 bg-white/20"
            style={{ left: percent(tick.tsMs) }}
            title={`${Math.max(0, Math.floor((tick.payload.ms_left as number) / 1000))}s left`}
          />
        ))}
        {deathEvents.map((event) => (
          <div
            key={event.seq}
            className="absolute top-1/2 flex -translate-y-1/2 items-center text-danger"
            style={{ left: percent(event.tsMs) }}
          >
            ✖
          </div>
        ))}
        {respawns.map((event) => (
          <div
            key={event.seq}
            className="absolute top-1/2 flex -translate-y-1/2 items-center text-warning"
            style={{ left: percent(event.tsMs) }}
          >
            ⟳
          </div>
        ))}
        {diaries.map((entry, index) => {
          const key = diaryKey(agentId, entry)
          const isSelected = key === selectedKey
          const highlighted = highlightedKeys.has(key)
          return (
            <button
              key={`${entry.created_at}-${index}`}
              type='button'
              onClick={(event) => {
                event.stopPropagation()
                onSelectDiary(agentId, entry)
              }}
              className={clsx(
                'absolute -translate-x-1/2 rounded-full border px-3 py-1 text-xs transition',
                highlighted ? 'border-accent/60 bg-accent/20 text-white' : 'border-white/10 bg-white/10 text-slate-200',
                isSelected && 'ring-2 ring-accent/60',
              )}
              style={{ left: percent(entry.createdAtMs), top: '20%' }}
            >
              {Math.max(0, Math.floor(entry.tick_ms_left / 1000))}s · Life {entry.life_index}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export const diaryKey = (agentId: string, entry: NormalizedDiaryEntry) => `${agentId}-${entry.createdAtMs}`
