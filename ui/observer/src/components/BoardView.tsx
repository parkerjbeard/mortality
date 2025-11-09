import { useEffect, useState } from 'react'
import { NormalizedBundle, NormalizedEvent } from '@/lib/bundle'
import { AgentSnapshot } from '@/lib/derive'
import { PlaybackControls } from '@/hooks/usePlayback'
import { AgentCard } from './AgentCard'
import { AgentDrawer } from './AgentDrawer'
import { EventFilter, EventStream } from './EventStream'

interface BoardViewProps {
  bundle: NormalizedBundle
  events: NormalizedEvent[]
  snapshots: Record<string, AgentSnapshot>
  playback: PlaybackControls
}

export const BoardView = ({
  bundle,
  events,
  snapshots,
  playback,
}: BoardViewProps) => {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(
    bundle.agentOrder[0] ?? null,
  )
  const [activeFilters, setActiveFilters] = useState<Set<EventFilter>>(
    () =>
      new Set<EventFilter>([
        'interaction',
        'message',
        'tool',
        'diary',
        'tick',
        'death',
        'respawn',
      ]),
  )

  useEffect(() => {
    setSelectedAgent(bundle.agentOrder[0] ?? null)
  }, [bundle])

  const observationFeed: string[] = Array.isArray(bundle.raw.metadata.deaths)
    ? bundle.raw.metadata.deaths
    : []

  const agentCards = bundle.agentOrder
    .map((agentId) => snapshots[agentId])
    .filter(Boolean)

  const toggleFilter = (filter: EventFilter) => {
    setActiveFilters((current) => {
      const next = new Set(current)
      if (next.has(filter)) {
        next.delete(filter)
      } else {
        next.add(filter)
      }
      return next
    })
  }

  const selectedSnapshot = selectedAgent ? snapshots[selectedAgent] : undefined

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
      <div className="space-y-6">
        <EventStream
          bundle={bundle}
          events={events}
          activeFilters={activeFilters}
          onToggleFilter={toggleFilter}
          onJump={(ts) => {
            playback.seekMs(ts)
            playback.setPlaying(false)
          }}
        />
        {observationFeed.length > 0 && (
          <div className="rounded-2xl border border-white/5 bg-white/5 p-4">
            <h3 className="text-sm font-semibold text-white">
              Observation Board
            </h3>
            <ul className="mt-3 space-y-2 text-sm text-slate-300">
              {observationFeed.map((line, index) => (
                <li
                  key={`${line}-${index}`}
                  className="rounded-xl bg-black/20 p-3"
                >
                  {line}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <div className="relative">
        <div className="grid gap-4 md:grid-cols-2">
          {agentCards.map((snapshot) => (
            <AgentCard
              key={snapshot.agentId}
              snapshot={snapshot}
              onSelect={() => setSelectedAgent(snapshot.agentId)}
              selected={selectedAgent === snapshot.agentId}
            />
          ))}
          {agentCards.length === 0 && (
            <p className="rounded-3xl border border-white/5 bg-white/5 p-6 text-sm text-slate-400">
              No agents detected in this bundle.
            </p>
          )}
        </div>
        {selectedAgent && (
          <AgentDrawer
            agentId={selectedAgent}
            bundle={bundle}
            events={events}
            playheadMs={playback.playheadMs}
            onClose={() => setSelectedAgent(null)}
          />
        )}
      </div>
    </div>
  )
}
