import { AgentSnapshot } from '@/lib/derive'
import { formatCountdown } from '@/lib/time'
import clsx from 'clsx'
import { CountdownRing } from './CountdownRing'

interface AgentCardProps {
  snapshot: AgentSnapshot
  onSelect: () => void
  selected: boolean
}

export const AgentCard = ({ snapshot, onSelect, selected }: AgentCardProps) => {
  const statusTone = getStatusTone(snapshot.status)
  const label = formatCountdown(snapshot.msLeft)
  return (
    <button
      type="button"
      onClick={onSelect}
      className={clsx(
        'flex flex-col gap-3 rounded-3xl border p-4 text-left transition',
        selected ? 'border-accent/60 bg-accent/10' : 'border-white/5 bg-white/5 hover:border-white/20',
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-400">{snapshot.profile.archetype}</p>
          <h4 className="text-lg font-semibold text-white">{snapshot.profile.display_name}</h4>
        </div>
        <span
          className={clsx(
            'rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide',
            statusTone.bg,
            statusTone.text,
          )}
        >
          {snapshot.status}
        </span>
      </div>
      <div className="flex items-center gap-4">
        <CountdownRing value={snapshot.msLeft} max={snapshot.timerDurationMs} label={label} />
        <div className="flex-1 space-y-2 text-sm text-slate-300">
          <p className="line-clamp-2">{snapshot.profile.summary}</p>
          {snapshot.lastDiary && (
            <p className="line-clamp-2 text-slate-400">
              <span className="font-semibold text-slate-200">Diary:</span> {snapshot.lastDiary.text}
            </p>
          )}
          {snapshot.lastChunk && (
            <p className="line-clamp-1 text-slate-400">
              <span className="font-semibold text-slate-200">Stream:</span> {snapshot.lastChunk}
            </p>
          )}
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
