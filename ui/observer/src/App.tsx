import { useMemo, useState } from 'react'
import { NormalizedBundle } from '@/lib/bundle'
import { usePlayback } from '@/hooks/usePlayback'
import { deriveAgentSnapshots } from '@/lib/derive'
import { BundleLoader } from '@/components/BundleLoader'
import { PlaybackBar } from '@/components/PlaybackBar'
import { ViewToggle } from '@/components/ViewToggle'
import { BoardView } from '@/components/BoardView'
import { TimelineView } from '@/components/TimelineView'
import { formatDuration, formatTimestamp } from '@/lib/time'

const App = () => {
  const [bundle, setBundle] = useState<NormalizedBundle | null>(null)
  const [view, setView] = useState<'board' | 'timeline'>('board')
  const timeline = bundle?.timeline ?? { startMs: 0, endMs: 1 }
  const playback = usePlayback(timeline)

  const snapshots = useMemo(
    () => (bundle ? deriveAgentSnapshots(bundle, playback.playheadMs) : {}),
    [bundle, playback.playheadMs],
  )

  const eventsForView = useMemo(() => {
    if (!bundle) return []
    return bundle.events.filter((event) => event.tsMs <= playback.playheadMs)
  }, [bundle, playback.playheadMs])

  const handleBundleLoaded = (next: NormalizedBundle) => {
    setBundle(next)
    playback.seekMs(next.timeline.startMs)
    playback.setPlaying(false)
  }

  const llmProvider =
    bundle && typeof bundle.raw.llm.provider === 'string'
      ? bundle.raw.llm.provider
      : 'Custom LLM'
  const llmModel =
    bundle && typeof bundle.raw.llm.model === 'string' ? bundle.raw.llm.model : 'Model'

  return (
    <div className="min-h-screen bg-canvas pb-16 text-slate-100">
      <div className="mx-auto max-w-6xl space-y-8 px-4 py-10">
        <header className="flex flex-col gap-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.3em] text-slate-500">
                Mortality Observer
              </p>
              <h1 className="text-3xl font-semibold text-white">
                {bundle?.raw.experiment.slug ?? 'Observation console'}
              </h1>
              <p className="max-w-xl text-sm text-slate-400">
                {bundle?.raw.experiment.description ??
                  'Load a telemetry bundle to watch emergent behaviour play out across long-form agent lives.'}
              </p>
            </div>
            <BundleLoader onLoaded={handleBundleLoaded} />
          </div>
          {bundle && (
            <div className="grid gap-3 md:grid-cols-3">
              <Stat
                label="Agents"
                value={bundle.agentOrder.length.toString()}
                hint="active participants"
              />
              <Stat
                label="Recorded Window"
                value={formatDuration(bundle.timeline.durationMs)}
                hint={`${formatTimestamp(bundle.timeline.startMs)} → ${formatTimestamp(bundle.timeline.endMs)}`}
              />
              <Stat label="LLM Provider" value={llmProvider} hint={llmModel} />
            </div>
          )}
        </header>
        {bundle ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-3xl border border-white/5 bg-panel/30 p-4 text-sm text-slate-400">
              <span>
                Exported{' '}
                {new Date(bundle.raw.exported_at).toLocaleString(undefined, {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
              <span>
                Lifespan captured:{' '}
                <span className="text-white">
                  {formatTimestamp(bundle.timeline.startMs)} →{' '}
                  {formatTimestamp(bundle.timeline.endMs)}
                </span>
              </span>
            </div>
            <PlaybackBar playback={playback} bundle={bundle} />
            <ViewToggle view={view} onChange={setView} />
            {view === 'board' ? (
              <BoardView
                bundle={bundle}
                snapshots={snapshots}
                events={eventsForView}
                playback={playback}
              />
            ) : (
              <TimelineView
                bundle={bundle}
                snapshots={snapshots}
                playback={playback}
              />
            )}
          </>
        ) : (
          <div className="rounded-3xl border border-dashed border-white/10 bg-white/5 p-10 text-center text-slate-400">
            Load a telemetry bundle to unlock both dashboards. Use the CLI export
            flag or the sample files to get started.
          </div>
        )}
      </div>
    </div>
  )
}

interface StatProps {
  label: string
  value: string
  hint?: string
}

const Stat = ({ label, value, hint }: StatProps) => (
  <div className="rounded-2xl border border-white/5 bg-white/5 p-4">
    <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
    <p className="text-2xl font-semibold text-white">{value}</p>
    {hint && <p className="text-xs text-slate-500">{hint}</p>}
  </div>
)

export default App
