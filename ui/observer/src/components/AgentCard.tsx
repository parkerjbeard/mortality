import { AgentSnapshot } from '@/lib/derive'
import { formatCountdown, formatDuration } from '@/lib/time'
import clsx from 'clsx'

interface AgentCardProps {
  snapshot: AgentSnapshot
  onSelect: () => void
  selected: boolean
}

export const AgentCard = ({ snapshot, onSelect, selected }: AgentCardProps) => {
  const statusTone = getStatusTone(snapshot.status)
  const timerLabel = snapshot.msLeft !== null ? formatCountdown(snapshot.msLeft) : '—'
  const spanLabel =
    typeof snapshot.timerDurationMs === 'number' && snapshot.timerDurationMs > 0
      ? formatDuration(snapshot.timerDurationMs)
      : 'Open-ended'
  const insight = snapshot.lastDiary?.text ?? snapshot.profile.summary

  return (
    <button
      type="button"
      onClick={onSelect}
      className={clsx(
        'flex flex-col gap-3 rounded-3xl border p-4 text-left transition',
        selected ? 'border-accent/40 bg-accent/5' : 'border-white/5 bg-panel/30 hover:border-white/20',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">{snapshot.profile.archetype}</p>
          <h4 className="text-lg font-semibold text-white">{snapshot.profile.display_name}</h4>
        </div>
        <span
          className={clsx(
            'rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide',
            statusTone.bg,
            statusTone.text,
          )}
        >
          {snapshot.status}
        </span>
      </div>
      <p className="text-sm text-slate-300 line-clamp-3">{insight}</p>
      {snapshot.lastChunk && (
        <p className="text-xs text-slate-500 line-clamp-2">
          <span className="font-semibold text-slate-300">Stream:</span> {snapshot.lastChunk}
        </p>
      )}
      <div className="text-xs text-slate-500">
        <div className="flex items-center justify-between">
          <span>Life {snapshot.lifeIndex}</span>
          <span>{spanLabel}</span>
        </div>
        <div className="mt-1 flex items-center justify-between">
          <span>Tick: {snapshot.tickSeconds ? `${snapshot.tickSeconds}s` : '—'}</span>
          <span>{timerLabel} left</span>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 text-xs text-slate-400">
        {snapshot.profile.traits.slice(0, 4).map((trait) => (
          <span key={trait} className="rounded-full bg-white/5 px-2 py-0.5">
            {trait}
          </span>
        ))}
      </div>
    </button>
  )
}

const getStatusTone = (status: AgentSnapshot['status']) => {
  switch (status) {
    case 'expired':
      return { bg: 'bg-danger/20', text: 'text-danger' }
    case 'respawning':
      return { bg: 'bg-warning/20', text: 'text-warning' }
    case 'alive':
      return { bg: 'bg-accent/20', text: 'text-accent' }
    default:
      return { bg: 'bg-white/10', text: 'text-slate-200' }
  }
}
