import { useMemo } from 'react'
import { NormalizedBundle, NormalizedEvent } from '@/lib/bundle'
import { formatTimestamp } from '@/lib/time'
import clsx from 'clsx'

interface InteractionFeedProps {
  bundle: NormalizedBundle
  events: NormalizedEvent[]
  onJump: (tsMs: number) => void
  limit?: number
}

interface InteractionEntry {
  id: string
  tsMs: number
  agentId: string
  direction: string
  role: string
  content: string
}

export const InteractionFeed = ({
  bundle,
  events,
  onJump,
  limit = 40,
}: InteractionFeedProps) => {
  const entries = useMemo(
    () => buildEntries(bundle, events, limit),
    [bundle, events, limit],
  )

  return (
    <section className="rounded-3xl border border-white/5 bg-panel/40 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
            Live interactions
          </p>
          <p className="text-sm text-slate-300">
            Messages exchanged up to this moment
          </p>
        </div>
        <span className="text-xs text-slate-500">{entries.length} shown</span>
      </div>
      <ul className="mt-4 space-y-2">
        {entries.map((entry) => {
          const profile = bundle.agents[entry.agentId]
          const name = profile?.display_name ?? entry.agentId
          return (
            <li key={entry.id}>
              <button
                type="button"
                onClick={() => onJump(entry.tsMs)}
                className="w-full rounded-2xl border border-white/5 bg-white/5 p-3 text-left transition hover:border-white/20 hover:bg-white/10"
              >
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span className="font-semibold text-slate-300">{name}</span>
                  <span>{formatTimestamp(entry.tsMs)}</span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wide">
                  <span
                    className={clsx(
                      'rounded-full px-2 py-0.5',
                      entry.direction === 'inbound'
                        ? 'bg-emerald-500/10 text-emerald-200'
                        : 'bg-sky-500/10 text-sky-200',
                    )}
                  >
                    {entry.direction === 'inbound' ? 'inbound' : 'outbound'}
                  </span>
                  {entry.role && (
                    <span className="rounded-full bg-white/10 px-2 py-0.5 text-slate-300">
                      {entry.role}
                    </span>
                  )}
                </div>
                <p className="mt-2 text-sm text-slate-100 line-clamp-3">
                  {entry.content}
                </p>
              </button>
            </li>
          )
        })}
        {entries.length === 0 && (
          <li className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-3 text-xs text-slate-500">
            No interactions logged yet at this timestamp.
          </li>
        )}
      </ul>
    </section>
  )
}

const buildEntries = (
  bundle: NormalizedBundle,
  events: NormalizedEvent[],
  limit: number,
): InteractionEntry[] => {
  const filtered = events.filter((event) => event.event === 'agent.message')
  const sliced = filtered.slice(-limit)
  return sliced
    .map((event) => {
      const agentId = String(
        event.payload.agent_id || event.payload.profile?.agent_id || '',
      )
      if (!agentId) {
        return null
      }
      const direction =
        typeof event.payload.direction === 'string'
          ? event.payload.direction
          : 'outbound'
      const role =
        typeof event.payload.message?.role === 'string'
          ? event.payload.message.role
          : ''
      const content = normalizeContent(event.payload.message?.content)
      return {
        id: `msg-${event.seq}`,
        tsMs: event.tsMs,
        agentId,
        direction,
        role,
        content,
      }
    })
    .filter((entry): entry is InteractionEntry =>
      Boolean(entry && entry.content),
    )
    .sort((a, b) => b.tsMs - a.tsMs)
}

const normalizeContent = (value: unknown): string => {
  if (typeof value === 'string') {
    return value
  }
  if (Array.isArray(value)) {
    return value
      .map((chunk) =>
        typeof chunk === 'string' ? chunk : JSON.stringify(chunk),
      )
      .join(' ')
  }
  if (value && typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch (error) {
      console.error('Failed to stringify interaction content', error)
    }
  }
  return '—'
}
