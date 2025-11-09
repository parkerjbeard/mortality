import { NormalizedDiaryEntry } from '@/lib/bundle'
import { formatTimestamp } from '@/lib/time'

interface TimelineDetailProps {
  entry?: NormalizedDiaryEntry
  agentName?: string
}

export const TimelineDetail = ({ entry, agentName }: TimelineDetailProps) => {
  if (!entry || !agentName) {
    return (
      <div className="rounded-3xl border border-white/5 bg-white/5 p-4 text-sm text-slate-400">
        Select a diary or marker to inspect the underlying log line.
      </div>
    )
  }
  return (
    <div className="rounded-3xl border border-white/5 bg-white/5 p-4">
      <p className="text-xs uppercase tracking-wide text-slate-400">Agent</p>
      <h3 className="text-lg font-semibold text-white">{agentName}</h3>
      <dl className="mt-3 space-y-1 text-sm text-slate-300">
        <div className="flex justify-between">
          <dt>Timestamp</dt>
          <dd>{formatTimestamp(entry.createdAtMs)}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Life</dt>
          <dd>{entry.life_index}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Tick</dt>
          <dd>{Math.max(0, Math.floor(entry.tick_ms_left / 1000))}s left</dd>
        </div>
      </dl>
      <p className="mt-4 whitespace-pre-wrap text-sm text-slate-100">{entry.text}</p>
      {entry.tags?.length ? (
        <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-wide text-slate-400">
          {entry.tags.map((tag) => (
            <span key={tag} className="rounded-full bg-white/10 px-2 py-0.5">
              {tag}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  )
}
