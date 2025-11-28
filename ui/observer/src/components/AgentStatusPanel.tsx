import { useMemo } from 'react'
import { AgentProfile } from '@/lib/bundle'
import { AgentTimer } from '@/hooks/useLiveConnection'

interface AgentStatusPanelProps {
  agents: Record<string, AgentProfile & { session?: { provider: string; model: string } }>
  timers: Record<string, AgentTimer>
}

const avatarPalette = [
  'border-emerald-500/50 bg-emerald-500/10 text-emerald-100',
  'border-sky-500/50 bg-sky-500/10 text-sky-100',
  'border-purple-500/50 bg-purple-500/10 text-purple-100',
  'border-amber-500/50 bg-amber-500/10 text-amber-100',
  'border-rose-500/50 bg-rose-500/10 text-rose-100',
]

const statusColors: Record<string, string> = {
  active: 'bg-emerald-500',
  expired: 'bg-amber-500',
  dead: 'bg-rose-500',
}

export const AgentStatusPanel = ({ agents, timers }: AgentStatusPanelProps) => {
  const agentList = useMemo(() => {
    return Object.entries(agents).map(([agentId, profile], index) => ({
      agentId,
      profile,
      timer: timers[agentId],
      colorIndex: index % avatarPalette.length,
    }))
  }, [agents, timers])

  if (agentList.length === 0) {
    return (
      <section className="rounded-3xl border border-dashed border-white/10 bg-white/5 p-6 text-center text-slate-400">
        <p className="text-sm">Waiting for agents to spawn...</p>
        <p className="mt-2 text-xs text-slate-500">
          Agents will appear here once the experiment starts
        </p>
      </section>
    )
  }

  return (
    <section className="rounded-3xl border border-white/5 bg-panel/60 p-4">
      <div className="mb-4">
        <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
          Active Council
        </p>
        <p className="text-sm text-slate-300">
          {agentList.filter((a) => a.timer?.status === 'active').length} of{' '}
          {agentList.length} agents alive
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {agentList.map(({ agentId, profile, timer, colorIndex }) => (
          <AgentCard
            key={agentId}
            profile={profile}
            timer={timer}
            colorClass={avatarPalette[colorIndex]}
          />
        ))}
      </div>
    </section>
  )
}

interface AgentCardProps {
  profile: AgentProfile & { session?: { provider: string; model: string } }
  timer?: AgentTimer
  colorClass: string
}

const AgentCard = ({ profile, timer, colorClass }: AgentCardProps) => {
  const status = timer?.status ?? 'pending'
  const msLeft = timer?.ms_left ?? 0
  const durationMs = timer?.duration_ms ?? 1

  const progress = Math.max(0, Math.min(100, (msLeft / durationMs) * 100))
  const minutes = Math.floor(msLeft / 60000)
  const seconds = Math.floor((msLeft % 60000) / 1000)
  const timeDisplay = `${minutes}:${seconds.toString().padStart(2, '0')}`

  const initials = profile.display_name
    .split(/[\s_-]+/)
    .slice(0, 2)
    .map((word) => word.charAt(0).toUpperCase())
    .join('')

  return (
    <div
      className={`rounded-2xl border border-white/5 bg-white/5 p-3 transition ${
        status === 'dead' ? 'opacity-50' : ''
      }`}
    >
      <div className="flex items-start gap-3">
        <span
          className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border text-xs font-semibold uppercase tracking-wide ${colorClass}`}
        >
          {initials}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold text-slate-200">
              {profile.display_name}
            </span>
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${statusColors[status] ?? 'bg-slate-500'} ${
                status === 'active' ? 'animate-pulse' : ''
              }`}
            />
          </div>
          <p className="truncate text-xs text-slate-500">{profile.archetype}</p>
        </div>
      </div>

      {timer && (
        <div className="mt-3 space-y-1">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-500">
              {status === 'dead'
                ? 'Expired'
                : status === 'expired'
                  ? 'Timer ended'
                  : 'Remaining'}
            </span>
            <span
              className={`font-mono ${
                status === 'active'
                  ? progress < 20
                    ? 'text-rose-400'
                    : progress < 40
                      ? 'text-amber-400'
                      : 'text-emerald-400'
                  : 'text-slate-500'
              }`}
            >
              {status === 'dead' || status === 'expired' ? '0:00' : timeDisplay}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
            <div
              className={`h-full transition-all duration-1000 ease-linear ${
                status === 'active'
                  ? progress < 20
                    ? 'bg-rose-500'
                    : progress < 40
                      ? 'bg-amber-500'
                      : 'bg-emerald-500'
                  : 'bg-slate-600'
              }`}
              style={{ width: `${status === 'active' ? progress : 0}%` }}
            />
          </div>
        </div>
      )}

      {profile.session && (
        <div className="mt-2 truncate text-[10px] text-slate-600">
          {profile.session.provider}: {profile.session.model}
        </div>
      )}
    </div>
  )
}
