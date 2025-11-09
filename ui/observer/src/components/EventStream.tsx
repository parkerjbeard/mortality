import { NormalizedBundle, NormalizedEvent } from '@/lib/bundle'
import clsx from 'clsx'

export type EventFilter = 'interaction' | 'message' | 'tool' | 'diary' | 'tick' | 'death' | 'respawn'

const filterDefinitions: Record<EventFilter, string[]> = {
  interaction: ['agent.chunk'],
  message: ['agent.message'],
  tool: ['agent.tool_call', 'agent.tool_result'],
  diary: ['agent.diary_entry'],
  tick: ['timer.tick'],
  death: ['agent.death'],
  respawn: ['agent.respawn'],
}

const filterLabels: Record<EventFilter, string> = {
  interaction: 'Interactions',
  message: 'Messages',
  tool: 'Tool Calls',
  diary: 'Diaries',
  tick: 'Ticks',
  death: 'Deaths',
  respawn: 'Respawns',
}

interface EventStreamProps {
  bundle: NormalizedBundle
  events: NormalizedEvent[]
  activeFilters: Set<EventFilter>
  onToggleFilter: (filter: EventFilter) => void
  onJump?: (tsMs: number) => void
}

export const EventStream = ({ bundle, events, activeFilters, onToggleFilter, onJump }: EventStreamProps) => {
  const entries = events
    .filter((event) => {
      const kind = mapKind(event)
      if (!kind) return false
      return activeFilters.has(kind)
    })
    .slice(-60)
    .reverse()

  return (
    <div className="rounded-2xl border border-white/5 bg-panel/70 p-4 shadow-lg shadow-black/40">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">Event Stream</h3>
        <span className="text-xs text-slate-500">Latest {entries.length} · click to scrub</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {(Object.keys(filterDefinitions) as EventFilter[]).map((filter) => (
          <button
            key={filter}
            type="button"
            onClick={() => onToggleFilter(filter)}
            className={clsx(
              'rounded-full border px-3 py-1 text-xs font-semibold transition',
              activeFilters.has(filter)
                ? 'border-accent/60 bg-accent/10 text-white'
                : 'border-white/10 bg-white/5 text-slate-400 hover:border-white/30 hover:text-white',
            )}
          >
            {filterLabels[filter]}
          </button>
        ))}
      </div>
      <ul className="mt-4 space-y-2 text-sm">
        {entries.map((event) => {
          const agentId = event.payload.agent_id as string | undefined
          const label = describeEvent(event)
          const agentName = agentId ? bundle.agents[agentId]?.display_name ?? agentId : 'System'
          return (
            <li
              key={event.seq}
              className="cursor-pointer rounded-xl border border-white/5 bg-white/5 px-3 py-2 text-slate-200 transition hover:border-accent/40 hover:bg-accent/5"
              onClick={() => onJump?.(event.tsMs)}
            >
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>{agentName}</span>
                <span>{new Date(event.ts).toLocaleTimeString()}</span>
              </div>
              <p className="mt-1 text-sm text-white">{label}</p>
            </li>
          )
        })}
        {entries.length === 0 && <li className="text-sm text-slate-500">No events match the current filters.</li>}
      </ul>
    </div>
  )
}

const mapKind = (event: NormalizedEvent): EventFilter | undefined => {
  return (Object.keys(filterDefinitions) as EventFilter[]).find((kind) => filterDefinitions[kind].includes(event.event))
}

const describeEvent = (event: NormalizedEvent): string => {
  switch (event.event) {
    case 'agent.message': {
      const direction = event.payload.direction === 'inbound' ? 'Prompt' : 'Reply'
      const role = typeof event.payload.message?.role === 'string' ? event.payload.message.role : 'unknown'
      const content = event.payload.message?.content
      const snippet = formatContentSnippet(content)
      return `${direction} (${role}): ${snippet}`
    }
    case 'agent.tool_call': {
      const name = String(event.payload.tool_call?.name ?? 'tool')
      const args = event.payload.tool_call?.arguments
      const preview = truncate(stringifyMaybeJson(args), 120)
      return `Invoked ${name} ${preview ? `with ${preview}` : ''}`.trim()
    }
    case 'agent.tool_result': {
      const body = event.payload.content ?? event.payload.tool_call?.result
      const preview = formatContentSnippet(body)
      return `Tool result: ${preview}`
    }
    case 'agent.chunk': {
      const content = typeof event.payload.content === 'string' ? event.payload.content : ''
      return content || `Streamed ${event.payload.content_size ?? 0} tokens`
    }
    case 'agent.diary_entry':
      return (event.payload.entry?.text as string) ?? 'Logged diary entry'
    case 'timer.tick':
      return `Tick ${event.payload.tick_index ?? 0}: ${event.payload.ms_left ?? 0} ms remaining`
    case 'agent.death':
      return 'Timer expired'
    case 'agent.respawn':
      return `Respawned into life #${event.payload.life_index ?? 1}`
    default:
      return event.event
  }
}

const formatContentSnippet = (value: unknown): string => {
  if (typeof value === 'string') {
    return truncate(value, 160)
  }
  if (Array.isArray(value)) {
    const text = value
      .map((part) => {
        if (typeof part === 'string') return part
        if (part && typeof part === 'object' && 'text' in part && typeof (part as { text?: unknown }).text === 'string') {
          return String((part as { text?: string }).text)
        }
        return ''
      })
      .filter(Boolean)
      .join(' ')
    return truncate(text, 160)
  }
  if (value && typeof value === 'object') {
    if ('text' in value && typeof (value as { text?: unknown }).text === 'string') {
      return truncate(String((value as { text?: string }).text), 160)
    }
    return truncate(stringifyMaybeJson(value), 160)
  }
  return ''
}

const stringifyMaybeJson = (value: unknown): string => {
  if (value === undefined || value === null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

const truncate = (text: string, limit: number): string => {
  if (!text) return ''
  if (text.length <= limit) return text
  return `${text.slice(0, limit - 1)}…`
}
