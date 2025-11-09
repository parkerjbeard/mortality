import { useMemo, useRef, useState } from 'react'
import { NormalizedBundle, NormalizedDiaryEntry } from '@/lib/bundle'
import { AgentSnapshot } from '@/lib/derive'
import { PlaybackControls } from '@/hooks/usePlayback'
import { TimelineLane, diaryKey } from './TimelineLane'
import { TimelineDetail } from './TimelineDetail'

interface TimelineViewProps {
  bundle: NormalizedBundle
  snapshots: Record<string, AgentSnapshot>
  playback: PlaybackControls
}

const laneHeight = 220
const laneGap = 28
const paddingY = 16
const trackCenterOffset = 120

export const TimelineView = ({ bundle, snapshots, playback }: TimelineViewProps) => {
  const [selection, setSelection] = useState<{ agentId: string; entry: NormalizedDiaryEntry } | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const totalHeight =
    paddingY * 2 + bundle.agentOrder.length * laneHeight + Math.max(0, bundle.agentOrder.length - 1) * laneGap
  const playheadMs = playback.playheadMs
  const visibleConnectors = useMemo(
    () =>
      bundle.connectors.filter(
        (connector) => connector.fromTs <= playheadMs && connector.toTs <= playheadMs,
      ),
    [bundle.connectors, playheadMs],
  )
  const highlightedKeys = useMemo(() => {
    const set = new Set<string>()
    visibleConnectors.forEach((connector) => set.add(`${connector.toAgentId}-${connector.toTs}`))
    return set
  }, [visibleConnectors])

  const handleTimelineClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const bounds = containerRef.current?.getBoundingClientRect()
    if (!bounds) return
    const fraction = (event.clientX - bounds.left) / bounds.width
    playback.seekFraction(fraction)
    playback.setPlaying(false)
  }

  const playheadPercent = `${Math.min(100, Math.max(0, playback.progress * 100)).toFixed(2)}%`

  const laneCenters = bundle.agentOrder.reduce<Record<string, number>>((acc, agentId, index) => {
    acc[agentId] = paddingY + index * (laneHeight + laneGap) + trackCenterOffset
    return acc
  }, {})

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div
        ref={containerRef}
        className="relative rounded-3xl border border-white/5 bg-white/5 p-4"
        onClick={handleTimelineClick}
      >
        <div className="flex flex-col" style={{ gap: `${laneGap}px` }}>
          {bundle.agentOrder.map((agentId) => (
            <div key={agentId} style={{ minHeight: laneHeight }}>
              <TimelineLane
                bundle={bundle}
                agentId={agentId}
                snapshot={snapshots[agentId]}
                onSelectDiary={(id, entry) => {
                  setSelection({ agentId: id, entry })
                }}
                selectedKey={selection ? diaryKey(selection.agentId, selection.entry) : null}
                highlightedKeys={highlightedKeys}
              />
            </div>
          ))}
        </div>
        <svg className="pointer-events-none absolute left-0 top-0" width="100%" height={totalHeight}>
          {visibleConnectors.map((connector, index) => {
            const fromY = laneCenters[connector.fromAgentId]
            const toY = laneCenters[connector.toAgentId]
            if (fromY === undefined || toY === undefined) {
              return null
            }
            const fromX = percentOfTimeline(bundle, connector.fromTs)
            const toX = percentOfTimeline(bundle, connector.toTs)
            return (
              <line
                key={`${connector.fromAgentId}-${index}-${connector.toAgentId}`}
                x1={`${fromX}%`}
                y1={fromY}
                x2={`${toX}%`}
                y2={toY}
                stroke="rgba(74, 222, 128, 0.35)"
                strokeWidth={2}
                strokeDasharray="6 6"
              />
            )
          })}
        </svg>
        <div
          className="pointer-events-none absolute top-4 bottom-4 w-[2px] bg-accent/60"
          style={{ left: playheadPercent }}
        >
          <div className="absolute -top-3 left-1/2 h-2 w-2 -translate-x-1/2 rounded-full bg-accent" />
        </div>
      </div>
      <TimelineDetail
        entry={selection?.entry}
        agentName={selection ? bundle.agents[selection.agentId]?.display_name : undefined}
      />
    </div>
  )
}

const percentOfTimeline = (bundle: NormalizedBundle, ts: number) => {
  const { startMs, durationMs } = bundle.timeline
  const raw = ((ts - startMs) / durationMs) * 100
  return Math.min(100, Math.max(0, raw))
}
