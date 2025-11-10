import {
  NormalizedBundle,
  NormalizedEvent,
  getAgentModelLabel,
} from '@/lib/bundle'
import { groupDiariesByLife } from '@/lib/derive'
import { formatTimestamp } from '@/lib/time'
import { AgentModelBadge } from './AgentModelBadge'

interface AgentDrawerProps {
  agentId: string
  bundle: NormalizedBundle
  events: NormalizedEvent[]
  playheadMs: number
  onClose: () => void
}

export const AgentDrawer = ({
  agentId,
  bundle,
  events,
  playheadMs,
  onClose,
}: AgentDrawerProps) => {
  const profile = bundle.agents[agentId]
  if (!profile) return null
  const modelLabel = getAgentModelLabel(bundle, agentId)
  const diaries = (bundle.diaries[agentId] ?? []).filter(
    (entry) => entry.createdAtMs <= playheadMs,
  )
  const diaryGroups = groupDiariesByLife(diaries)
  const chunks = events
    .filter(
      (event) =>
        event.event === 'agent.chunk' && event.payload.agent_id === agentId,
    )
    .slice(-40)
    .reverse()

  // Recent inbound/outbound message events for this agent
  const messages = events
    .filter(
      (event) =>
        event.event === 'agent.message' && event.payload.agent_id === agentId,
    )
    .slice(-60)
    .reverse()

  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-black/60 backdrop-blur" onClick={onClose} />
      <div className="flex w-full max-w-xl flex-col overflow-y-auto bg-panel/95 p-6 shadow-2xl shadow-black/80">
        <header className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-400">
              {profile.archetype}
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="text-2xl font-semibold text-white">
                {profile.display_name}
              </h2>
              <AgentModelBadge label={modelLabel} />
            </div>
            <p className="text-sm text-slate-300">{profile.summary}</p>
          </div>
          <button
            type="button"
            className="text-slate-400 transition hover:text-white"
            onClick={onClose}
          >
            ✕
          </button>
        </header>
        <div className="mt-6 space-y-6">
          {/* Diary entries remain grouped by life to emphasize reflection vs. interaction */}
          {diaryGroups.map((group) => (
            <section key={group.lifeIndex}>
              <h3 className="text-sm font-semibold text-white">
                Life {group.lifeIndex}
              </h3>
              <ul className="mt-2 space-y-3">
                {group.entries.map((entry, index) => (
                  <li
                    key={`${entry.created_at}-${index}`}
                    className="rounded-2xl border border-white/5 bg-white/5 p-3"
                  >
                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <span>{formatTimestamp(entry.createdAtMs)}</span>
                      <span>
                        {Math.max(0, Math.floor(entry.tick_ms_left / 1000))}s
                        left
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-slate-100 whitespace-pre-wrap">
                      {entry.text}
                    </p>
                    {entry.tags?.length ? (
                      <div className="mt-2 flex flex-wrap gap-2 text-[11px] uppercase tracking-wide text-slate-400">
                        {entry.tags.map((tag) => (
                          <span
                            key={tag}
                            className="rounded-full bg-white/5 px-2 py-0.5"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          ))}
          {/* Delineated Agent Interaction Messages (discrete turns) */}
          <section>
            <h3 className="text-sm font-semibold text-white">Messages</h3>
            <ul className="mt-2 space-y-2 text-sm text-slate-200">
              {messages.map((event) => {
                const direction = String(event.payload.direction || '')
                const role = String(
                  (event.payload.message?.role as string) || '',
                )
                const content = String(
                  (event.payload.message?.content as string) || '',
                )
                return (
                  <li
                    key={`msg-${event.seq}`}
                    className="rounded-xl border border-white/5 bg-white/5 p-3"
                  >
                    <div className="flex items-center justify-between text-xs text-slate-500">
                      <span className="inline-flex items-center gap-2">
                        <span className="rounded-full bg-white/10 px-2 py-0.5 uppercase tracking-wide">
                          {direction || '—'}
                        </span>
                        {role && (
                          <span className="rounded-full bg-white/10 px-2 py-0.5 uppercase tracking-wide">
                            {role}
                          </span>
                        )}
                      </span>
                      <span>{formatTimestamp(event.tsMs)}</span>
                    </div>
                    {content && (
                      <p className="mt-1 whitespace-pre-wrap text-slate-100">
                        {content}
                      </p>
                    )}
                  </li>
                )
              })}
              {messages.length === 0 && (
                <li className="text-xs text-slate-500">
                  No messages recorded during this window.
                </li>
              )}
            </ul>
          </section>
          <section>
            <h3 className="text-sm font-semibold text-white">
              Streaming Output
            </h3>
            <ul className="mt-2 space-y-2 text-sm text-slate-200">
              {chunks.map((event) => (
                <li
                  key={event.seq}
                  className="rounded-xl border border-white/5 bg-white/5 p-3 text-slate-300"
                >
                  <span className="text-xs text-slate-500">
                    {formatTimestamp(event.tsMs)}
                  </span>
                  <p className="mt-1 text-slate-100">
                    {event.payload.content as string}
                  </p>
                </li>
              ))}
              {chunks.length === 0 && (
                <li className="text-xs text-slate-500">
                  No chunks recorded during this window.
                </li>
              )}
            </ul>
          </section>
        </div>
      </div>
    </div>
  )
}
