import { NormalizedBundle, NormalizedEvent } from '@/lib/bundle'
import { groupDiariesByLife } from '@/lib/derive'
import { formatTimestamp } from '@/lib/time'

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

  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-black/60 backdrop-blur" onClick={onClose} />
      <div className="flex w-full max-w-xl flex-col overflow-y-auto bg-panel/95 p-6 shadow-2xl shadow-black/80">
        <header className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-400">
              {profile.archetype}
            </p>
            <h2 className="text-2xl font-semibold text-white">
              {profile.display_name}
            </h2>
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
          <section>
            <h3 className="text-sm font-semibold text-white">
              Streamed Interactions
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
