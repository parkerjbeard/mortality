import { useMemo, useRef } from 'react'
import { NormalizedBundle, NormalizedEvent } from '@/lib/bundle'
import { getAgentDisplayName, getAgentInitials } from '@/lib/agents'
import { PlaybackControls } from '@/hooks/usePlayback'
import { formatTimestamp } from '@/lib/time'
import { EVENT_CATEGORY_LABELS, EventCategory } from '@/lib/filters'
import { useVirtualizer } from '@tanstack/react-virtual'

interface ChatReplayProps {
  bundle: NormalizedBundle
  events: NormalizedEvent[]
  playback: PlaybackControls
  onJump: (tsMs: number) => void
  activeCategories: Set<EventCategory>
}

type ChatCategory = Exclude<EventCategory, 'diary'>

interface ChatEntry {
  id: string
  tsMs: number
  agentId: string
  direction: string
  category: ChatCategory
  summary: string
}

const avatarPalette = [
  'border-emerald-500/50 bg-emerald-500/10 text-emerald-100',
  'border-sky-500/50 bg-sky-500/10 text-sky-100',
  'border-purple-500/50 bg-purple-500/10 text-purple-100',
  'border-amber-500/50 bg-amber-500/10 text-amber-100',
  'border-rose-500/50 bg-rose-500/10 text-rose-100',
]

export const ChatReplay = ({
  bundle,
  events,
  playback,
  onJump,
  activeCategories,
}: ChatReplayProps) => {
  const entries = useMemo(() => collectEntries(events), [events])
  const visibleEntries = useMemo(
    () => entries.filter((entry) => activeCategories.has(entry.category)),
    [entries, activeCategories],
  )

  const parentRef = useRef<HTMLDivElement | null>(null)
  const rowVirtualizer = useVirtualizer({
    count: visibleEntries.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 96,
    overscan: 8,
    getItemKey: (index) => visibleEntries[index]?.id ?? index,
  })
  const virtualItems = rowVirtualizer.getVirtualItems()
  const totalHeight = rowVirtualizer.getTotalSize()

  return (
    <section className="flex flex-col rounded-3xl border border-white/5 bg-panel/60 p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
            Live feed
          </p>
          <p className="text-sm text-slate-300">
            Showing actions until{' '}
            <span className="text-white">
              {formatTimestamp(playback.playheadMs)}
            </span>
          </p>
        </div>
        <span className="text-xs text-slate-500">
          {visibleEntries.length} event{visibleEntries.length === 1 ? '' : 's'}
        </span>
      </div>
      <div className="mt-4 flex flex-1 flex-col rounded-2xl border border-white/5 bg-black/20">
        <div
          ref={parentRef}
          className="max-h-[70vh] flex-1 overflow-y-auto p-4 pr-3"
        >
          {visibleEntries.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-6 text-center text-sm text-slate-500">
              No events match the active filters at this timestamp.
            </div>
          ) : (
            <div
              style={{ height: `${totalHeight}px`, position: 'relative' }}
              role="list"
            >
              {virtualItems.map((item) => {
                const entry = visibleEntries[item.index]
                const toneIndex = getToneIndex(bundle, entry.agentId)
                const tone = avatarPalette[toneIndex]
                const profile = bundle.agents[entry.agentId]
                const name = getAgentDisplayName(profile, entry.agentId)
                const initials = getAgentInitials(profile, entry.agentId)
                return (
                  <div
                    key={entry.id}
                    role="listitem"
                    className="absolute w-full pb-4"
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
                      className="group flex w-full items-center gap-3 rounded-2xl border border-white/5 bg-white/5 p-3 text-left text-slate-300 transition hover:border-white/30 hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                    >
                      <span
                        className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border text-xs font-semibold uppercase tracking-wide ${tone}`}
                      >
                        {initials}
                      </span>
                      <div className="flex min-w-0 flex-col gap-1">
                        <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wide text-slate-500">
                          <span className="font-semibold text-slate-200">
                            {name}
                          </span>
                          <span className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] text-slate-400">
                            {EVENT_CATEGORY_LABELS[entry.category]}
                          </span>
                        </div>
                        <p className="truncate text-sm text-slate-100">
                          {entry.summary}
                        </p>
                      </div>
                      <span className="ml-auto shrink-0 text-xs text-slate-500">
                        {formatTimestamp(entry.tsMs)}
                      </span>
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

const collectEntries = (events: NormalizedEvent[]): ChatEntry[] => {
  return events
    .map((event) => {
      const payload = event.payload as Record<string, unknown>
      if (event.event === 'agent.message') {
        return mapMessageEvent(event, payload)
      }
      if (
        event.event === 'agent.tool_call' ||
        event.event === 'agent.tool_result'
      ) {
        return mapToolEvent(event, payload)
      }
      return null
    })
    .filter((entry): entry is ChatEntry => entry !== null)
    .sort((a, b) => a.tsMs - b.tsMs)
}

const mapMessageEvent = (
  event: NormalizedEvent,
  payload: Record<string, unknown>,
): ChatEntry | null => {
  const agentId = extractAgentId(payload)
  if (!agentId) {
    return null
  }
  const messagePayload = payload['message'] as { role?: unknown } | undefined
  const directionValue = payload['direction']
  const direction =
    typeof directionValue === 'string' ? directionValue : 'outbound'
  const role =
    typeof messagePayload?.role === 'string' ? messagePayload.role : ''
  const category: ChatCategory = role === 'system' ? 'system' : 'broadcast'
  return {
    id: `msg-${event.seq}`,
    tsMs: event.tsMs,
    agentId,
    direction,
    category,
    summary: describeMessage(direction, role),
  }
}

const mapToolEvent = (
  event: NormalizedEvent,
  payload: Record<string, unknown>,
): ChatEntry | null => {
  const agentId = extractAgentId(payload)
  if (!agentId) {
    return null
  }
  return {
    id: `tool-${event.seq}`,
    tsMs: event.tsMs,
    agentId,
    direction: 'outbound',
    category: 'tool',
    summary: describeToolSummary(event.event, payload),
  }
}

const describeMessage = (direction: string, role: string): string => {
  const arrow = direction === 'inbound' ? '⇣' : '⇡'
  const directionLabel = direction === 'inbound' ? 'Inbound' : 'Outbound'
  const roleLabel = role ? role : 'message'
  return `${arrow} ${directionLabel} ${roleLabel}`.trim()
}

const describeToolSummary = (
  eventType: string,
  payload: Record<string, unknown>,
): string => {
  const toolCall = payload['tool_call'] as { name?: unknown } | undefined
  const rawName =
    typeof toolCall?.name === 'string' && toolCall.name.trim().length > 0
      ? toolCall.name.trim()
      : 'tool'
  if (eventType === 'agent.tool_call') {
    return `⇡ Requested ${rawName}`
  }
  const status = getToolStatus(payload)
  if (status) {
    return `⇣ ${rawName} → ${status}`
  }
  const error = payload['error']
  if (typeof error === 'string' && error.trim()) {
    return `⇣ ${rawName} error`
  }
  return `⇣ ${rawName} responded`
}

const getToolStatus = (payload: Record<string, unknown>): string | null => {
  const status = payload['status']
  if (typeof status === 'string' && status.trim()) {
    return status.trim()
  }
  const result = payload['result']
  if (typeof result === 'string' && result.trim()) {
    return result.trim()
  }
  return null
}

const getToneIndex = (bundle: NormalizedBundle, agentId: string): number => {
  const index = bundle.agentOrder.indexOf(agentId)
  if (index === -1) {
    return 0
  }
  return index % avatarPalette.length
}

const extractAgentId = (payload: Record<string, unknown>): string => {
  const direct = payload['agent_id']
  if (typeof direct === 'string') {
    return direct
  }
  if (typeof direct === 'number') {
    return String(direct)
  }
  const nested = payload['profile'] as { agent_id?: string } | undefined
  if (nested?.agent_id) {
    return nested.agent_id
  }
  return ''
}
