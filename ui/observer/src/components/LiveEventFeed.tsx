import { useEffect, useMemo, useRef, useState } from 'react'
import { AgentProfile, NormalizedEvent } from '@/lib/bundle'
import { formatTimestamp } from '@/lib/time'
import { useVirtualizer } from '@tanstack/react-virtual'

interface LiveEventFeedProps {
  events: NormalizedEvent[]
  agents: Record<string, AgentProfile>
  maxVisible?: number
}

type EventType = 'message' | 'tool' | 'diary' | 'timer' | 'death' | 'broadcast' | 'other'

interface FeedEntry {
  id: string
  tsMs: number
  agentId: string
  type: EventType
  summary: string
  detail?: string
}

const eventTypeColors: Record<EventType, string> = {
  message: 'bg-sky-500/20 text-sky-300',
  tool: 'bg-purple-500/20 text-purple-300',
  diary: 'bg-emerald-500/20 text-emerald-300',
  timer: 'bg-slate-500/20 text-slate-400',
  death: 'bg-rose-500/20 text-rose-300',
  broadcast: 'bg-amber-500/20 text-amber-300',
  other: 'bg-slate-500/20 text-slate-400',
}

const eventTypeLabels: Record<EventType, string> = {
  message: 'Message',
  tool: 'Tool',
  diary: 'Diary',
  timer: 'Timer',
  death: 'Death',
  broadcast: 'Broadcast',
  other: 'Event',
}

const avatarPalette = [
  'border-emerald-500/50 bg-emerald-500/10 text-emerald-100',
  'border-sky-500/50 bg-sky-500/10 text-sky-100',
  'border-purple-500/50 bg-purple-500/10 text-purple-100',
  'border-amber-500/50 bg-amber-500/10 text-amber-100',
  'border-rose-500/50 bg-rose-500/10 text-rose-100',
]

export const LiveEventFeed = ({
  events,
  agents,
  maxVisible = 200,
}: LiveEventFeedProps) => {
  const [autoScroll, setAutoScroll] = useState(true)
  const [filter, setFilter] = useState<EventType | 'all'>('all')
  const parentRef = useRef<HTMLDivElement | null>(null)

  const agentOrder = useMemo(() => Object.keys(agents).sort(), [agents])

  const entries = useMemo(() => {
    const mapped = events
      .map((event) => mapEventToEntry(event))
      .filter((entry): entry is FeedEntry => entry !== null)

    const filtered =
      filter === 'all' ? mapped : mapped.filter((e) => e.type === filter)

    return filtered.slice(-maxVisible)
  }, [events, filter, maxVisible])

  const rowVirtualizer = useVirtualizer({
    count: entries.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 72,
    overscan: 8,
    getItemKey: (index) => entries[index]?.id ?? index,
  })

  const virtualItems = rowVirtualizer.getVirtualItems()
  const totalHeight = rowVirtualizer.getTotalSize()

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (autoScroll && entries.length > 0 && parentRef.current) {
      parentRef.current.scrollTop = parentRef.current.scrollHeight
    }
  }, [entries.length, autoScroll])

  // Detect manual scroll
  const handleScroll = () => {
    if (!parentRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = parentRef.current
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 100
    setAutoScroll(isAtBottom)
  }

  return (
    <section className="flex flex-col rounded-3xl border border-white/5 bg-panel/60 p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
            Live Feed
          </p>
          <p className="text-sm text-slate-300">
            {entries.length} event{entries.length === 1 ? '' : 's'}
            {filter !== 'all' && ` (${eventTypeLabels[filter]})`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as EventType | 'all')}
            className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 focus:border-accent focus:outline-none"
          >
            <option value="all">All Events</option>
            <option value="message">Messages</option>
            <option value="diary">Diaries</option>
            <option value="tool">Tools</option>
            <option value="broadcast">Broadcasts</option>
            <option value="death">Deaths</option>
            <option value="timer">Timer</option>
          </select>
          <button
            type="button"
            onClick={() => setAutoScroll(!autoScroll)}
            className={`rounded-lg border px-2 py-1 text-xs transition ${
              autoScroll
                ? 'border-emerald-500/50 bg-emerald-500/20 text-emerald-300'
                : 'border-white/10 bg-white/5 text-slate-400 hover:bg-white/10'
            }`}
          >
            {autoScroll ? 'Auto-scroll ON' : 'Auto-scroll OFF'}
          </button>
        </div>
      </div>

      <div className="mt-4 flex flex-1 flex-col rounded-2xl border border-white/5 bg-black/20">
        <div
          ref={parentRef}
          onScroll={handleScroll}
          className="max-h-[60vh] flex-1 overflow-y-auto p-4 pr-3"
        >
          {entries.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-6 text-center text-sm text-slate-500">
              {filter === 'all'
                ? 'Waiting for events...'
                : `No ${eventTypeLabels[filter].toLowerCase()} events yet`}
            </div>
          ) : (
            <div
              style={{ height: `${totalHeight}px`, position: 'relative' }}
              role="list"
            >
              {virtualItems.map((item) => {
                const entry = entries[item.index]
                const toneIndex = agentOrder.indexOf(entry.agentId)
                const tone =
                  avatarPalette[
                    toneIndex === -1 ? 0 : toneIndex % avatarPalette.length
                  ]
                const profile = agents[entry.agentId]
                const name = profile?.display_name ?? entry.agentId
                const initials = name
                  .split(/[\s_-]+/)
                  .slice(0, 2)
                  .map((w) => w.charAt(0).toUpperCase())
                  .join('')

                return (
                  <div
                    key={entry.id}
                    role="listitem"
                    className="absolute w-full pb-3"
                    style={{
                      top: 0,
                      left: 0,
                      transform: `translateY(${item.start}px)`,
                    }}
                    ref={rowVirtualizer.measureElement}
                  >
                    <div className="flex items-start gap-3 rounded-2xl border border-white/5 bg-white/5 p-3 text-left text-slate-300">
                      <span
                        className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border text-[10px] font-semibold uppercase tracking-wide ${tone}`}
                      >
                        {initials}
                      </span>
                      <div className="flex min-w-0 flex-1 flex-col gap-1">
                        <div className="flex flex-wrap items-center gap-2 text-[11px]">
                          <span className="font-semibold text-slate-200">
                            {name}
                          </span>
                          <span
                            className={`rounded-full px-2 py-0.5 text-[10px] ${eventTypeColors[entry.type]}`}
                          >
                            {eventTypeLabels[entry.type]}
                          </span>
                          <span className="ml-auto text-slate-500">
                            {formatTimestamp(entry.tsMs)}
                          </span>
                        </div>
                        <p className="truncate text-sm text-slate-100">
                          {entry.summary}
                        </p>
                        {entry.detail && (
                          <p className="line-clamp-2 text-xs text-slate-500">
                            {entry.detail}
                          </p>
                        )}
                      </div>
                    </div>
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

const mapEventToEntry = (event: NormalizedEvent): FeedEntry | null => {
  const payload = event.payload as Record<string, unknown>
  const agentId = extractAgentId(payload)

  switch (event.event) {
    case 'agent.message': {
      const msg = payload.message as { role?: string; content?: unknown } | undefined
      const direction = payload.direction as string | undefined
      const arrow = direction === 'inbound' ? '⇣' : '⇡'
      const role = msg?.role ?? 'message'
      const content = extractContent(msg?.content)
      return {
        id: `msg-${event.seq}`,
        tsMs: event.tsMs,
        agentId,
        type: 'message',
        summary: `${arrow} ${role}`,
        detail: content ? truncate(content, 100) : undefined,
      }
    }

    case 'agent.tool_call': {
      const tool = payload.tool_call as { name?: string } | undefined
      return {
        id: `tool-call-${event.seq}`,
        tsMs: event.tsMs,
        agentId,
        type: 'tool',
        summary: `Called ${tool?.name ?? 'tool'}`,
      }
    }

    case 'agent.tool_result': {
      const tool = payload.tool_call as { name?: string } | undefined
      const content = payload.content as string | undefined
      return {
        id: `tool-result-${event.seq}`,
        tsMs: event.tsMs,
        agentId,
        type: 'tool',
        summary: `${tool?.name ?? 'tool'} responded`,
        detail: content ? truncate(content, 80) : undefined,
      }
    }

    case 'agent.diary_entry': {
      const entry = payload.entry as { text?: string; entry_index?: number } | undefined
      return {
        id: `diary-${event.seq}`,
        tsMs: event.tsMs,
        agentId,
        type: 'diary',
        summary: `Diary entry #${entry?.entry_index ?? '?'}`,
        detail: entry?.text ? truncate(entry.text, 100) : undefined,
      }
    }

    case 'agent.death':
      return {
        id: `death-${event.seq}`,
        tsMs: event.tsMs,
        agentId,
        type: 'death',
        summary: 'Agent died',
      }

    case 'agent.broadcast': {
      const text = payload.text as string | undefined
      return {
        id: `broadcast-${event.seq}`,
        tsMs: event.tsMs,
        agentId,
        type: 'broadcast',
        summary: 'Published broadcast',
        detail: text ? truncate(text, 80) : undefined,
      }
    }

    case 'timer.tick': {
      const msLeft = payload.ms_left as number | undefined
      const minutes = msLeft ? Math.floor(msLeft / 60000) : 0
      const seconds = msLeft ? Math.floor((msLeft % 60000) / 1000) : 0
      return {
        id: `tick-${event.seq}`,
        tsMs: event.tsMs,
        agentId,
        type: 'timer',
        summary: `Timer tick: ${minutes}:${seconds.toString().padStart(2, '0')} remaining`,
      }
    }

    case 'timer.expired':
      return {
        id: `expired-${event.seq}`,
        tsMs: event.tsMs,
        agentId,
        type: 'timer',
        summary: 'Timer expired',
      }

    case 'agent.spawned': {
      const profile = payload.profile as { display_name?: string } | undefined
      return {
        id: `spawned-${event.seq}`,
        tsMs: event.tsMs,
        agentId,
        type: 'other',
        summary: `${profile?.display_name ?? agentId} spawned`,
      }
    }

    default:
      return null
  }
}

const extractAgentId = (payload: Record<string, unknown>): string => {
  const direct = payload.agent_id
  if (typeof direct === 'string') return direct
  if (typeof direct === 'number') return String(direct)
  const profile = payload.profile as { agent_id?: string } | undefined
  return profile?.agent_id ?? 'unknown'
}

const extractContent = (content: unknown): string | undefined => {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    const texts = content
      .map((item) => {
        if (typeof item === 'string') return item
        if (typeof item === 'object' && item && 'text' in item) {
          return (item as { text?: string }).text
        }
        return undefined
      })
      .filter((t): t is string => !!t)
    return texts.join(' ')
  }
  return undefined
}

const truncate = (text: string, maxLength: number): string => {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength - 1) + '...'
}
