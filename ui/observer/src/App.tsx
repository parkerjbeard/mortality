import { useMemo, useState } from 'react'
import { BundleContext } from '@/lib/context'
import { NormalizedBundle } from '@/lib/bundle'
import { usePlayback } from '@/hooks/usePlayback'
import { deriveAgentSnapshots } from '@/lib/derive'
import { BundleLoader } from '@/components/BundleLoader'
import { PlaybackBar } from '@/components/PlaybackBar'
import { ViewToggle } from '@/components/ViewToggle'
import { BoardView } from '@/components/BoardView'
import { TimelineView } from '@/components/TimelineView'
import { formatDuration } from '@/lib/time'

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

  return (
    <BundleContext.Provider value={{ bundle, setBundle }}>
      <div className="min-h-screen bg-canvas pb-16 text-white">
        <div className="mx-auto max-w-7xl px-6 py-8 space-y-6">
          <header className="space-y-4">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
                Mortality Observer
              </p>
              <h1 className="text-3xl font-semibold text-white">
                Dual-interface telemetry viewer
              </h1>
              <p className="text-sm text-slate-400">
                Visualize countdown experiments as a strategic board or
                synchronized timeline.
              </p>
            </div>
            <BundleLoader onLoaded={handleBundleLoaded} />
          </header>
          {bundle ? (
            <>
              <div className="grid gap-4 md:grid-cols-3">
                <Stat
                  label="Experiment"
                  value={bundle.raw.experiment.slug}
                  hint={bundle.raw.experiment.description}
                />
                <Stat
                  label="Agents"
                  value={bundle.agentOrder.length.toString()}
                  hint="visible participants"
                />
                <Stat
                  label="Recorded Duration"
                  value={formatDuration(bundle.timeline.durationMs)}
                  hint={bundle.raw.llm.provider as string}
                />
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
              Load a telemetry bundle to unlock both dashboards. Use the CLI
              export flag or the sample files to get started.
            </div>
          )}
        </div>
      </div>
    </BundleContext.Provider>
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
