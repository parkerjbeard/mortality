import { useEffect, useState } from 'react'
import {
  NormalizedBundle,
  NormalizedEvent,
  getAgentModelLabel,
} from '@/lib/bundle'
import { AgentSnapshot } from '@/lib/derive'
import { PlaybackControls } from '@/hooks/usePlayback'
import { AgentCard } from './AgentCard'
import { AgentDrawer } from './AgentDrawer'
import { LifeFeed } from './LifeFeed'
import { InteractionFeed } from './InteractionFeed'

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

  useEffect(() => {
    setSelectedAgent(bundle.agentOrder[0] ?? null)
  }, [bundle])

  const agentCards = bundle.agentOrder
    .map((agentId) => {
      const snapshot = snapshots[agentId]
      if (!snapshot) {
        return null
      }
      return {
        snapshot,
        modelLabel: getAgentModelLabel(bundle, agentId),
      }
    })
    .filter(
      (entry): entry is { snapshot: AgentSnapshot; modelLabel: string } =>
        entry !== null,
    )

  const selectedSnapshot = selectedAgent ? snapshots[selectedAgent] : undefined

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
      <div className="space-y-6">
        <LifeFeed
          bundle={bundle}
          playback={playback}
          onJump={(ts) => {
            playback.seekMs(ts)
            playback.setPlaying(false)
          }}
        />
        <InteractionFeed
          bundle={bundle}
          events={events}
          onJump={(ts) => {
            playback.seekMs(ts)
            playback.setPlaying(false)
          }}
        />
      </div>
      <div className="relative space-y-5">
        <div className="grid gap-3 md:grid-cols-2">
          {agentCards.map(({ snapshot, modelLabel }) => (
            <AgentCard
              key={snapshot.agentId}
              snapshot={snapshot}
              onSelect={() => setSelectedAgent(snapshot.agentId)}
              selected={selectedAgent === snapshot.agentId}
              modelLabel={modelLabel}
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
