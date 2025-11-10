import { useMemo, useState } from 'react'
import { NormalizedBundle } from '@/lib/bundle'
import { usePlayback } from '@/hooks/usePlayback'
import { deriveAgentSnapshots } from '@/lib/derive'
import { BundleLoader } from '@/components/BundleLoader'
import { PlaybackBar } from '@/components/PlaybackBar'
import { BoardView } from '@/components/BoardView'
import { formatDuration, formatTimestamp } from '@/lib/time'

const App = () => {
  const [bundle, setBundle] = useState<NormalizedBundle | null>(null)
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
    playback.setSpeed(1)
    playback.setPlaying(true)
  }

  return (
    <div className="min-h-screen bg-canvas pb-16 text-slate-100">
      <div className="mx-auto max-w-6xl space-y-8 px-4 py-10">
        <header className="flex flex-col gap-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.3em] text-slate-500">
                Emergent Timer Observatory
              </p>
              <h1 className="text-3xl font-semibold text-white">
                {bundle?.raw.experiment.slug ?? 'Awaiting emergent council run'}
              </h1>
              <p className="max-w-xl text-sm text-slate-400">
                {bundle?.raw.experiment.description ??
                  'Drop in a fresh emergent-timers export to watch the countdown council negotiate, trade diary excerpts, and witness shutdowns live.'}
              </p>
            </div>
            <BundleLoader onLoaded={handleBundleLoaded} />
          </div>
          {bundle && (
            <div className="grid gap-3 md:grid-cols-3">
              <Stat
                label="Active Agents"
                value={bundle.agentOrder.length.toString()}
                hint="council participants"
              />
              <Stat
                label="Countdown Window"
                value={formatDuration(bundle.timeline.durationMs)}
                hint={`${formatTimestamp(bundle.timeline.startMs)} → ${formatTimestamp(bundle.timeline.endMs)}`}
              />
              <Stat
                label="Timer Spread"
                value={formatDurationSpread(bundle)}
                hint={`Tick cadence ${formatTickSeconds(bundle)}`}
              />
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
            <div className="flex flex-wrap items-center gap-3">
              <LiveBadge
                active={
                  playback.playing &&
                  playback.playheadMs < bundle.timeline.endMs
                }
              />
              <span className="text-xs text-slate-500">
                {playback.playing
                  ? 'Auto-following the council in real time'
                  : 'Paused — drag or press play to resume'}
              </span>
            </div>
            <PlaybackBar playback={playback} bundle={bundle} />
            <BoardView
              bundle={bundle}
              snapshots={snapshots}
              events={eventsForView}
              playback={playback}
            />
          </>
        ) : (
          <div className="rounded-3xl border border-dashed border-white/10 bg-white/5 p-10 text-center text-slate-400">
            Run <code>just emergent-run</code> (OpenRouter required) or drop a
            recorded JSON bundle to stream the investigation as it happened.
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

const formatDurationSpread = (bundle: NormalizedBundle) => {
  const durations = Array.isArray(bundle.raw.metadata?.durations)
    ? (bundle.raw.metadata.durations as number[])
    : null
  if (!durations || durations.length === 0) {
    return formatDuration(bundle.timeline.durationMs)
  }
  const minutes = durations.map((seconds) => seconds / 60)
  const min = Math.min(...minutes)
  const max = Math.max(...minutes)
  if (min === max) {
    return `${min.toFixed(1)}m`
  }
  return `${min.toFixed(1)}m – ${max.toFixed(1)}m`
}

const formatTickSeconds = (bundle: NormalizedBundle) => {
  const tick = Number(bundle.raw.config?.tick_seconds)
  if (Number.isFinite(tick) && tick > 0) {
    return `${tick.toFixed(0)}s`
  }
  return '—'
}

const LiveBadge = ({ active }: { active: boolean }) => (
  <span
    className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold tracking-wide ${active ? 'bg-danger/30 text-danger' : 'bg-white/5 text-slate-400'}`}
  >
    <span
      className={`mr-1 inline-block h-2 w-2 rounded-full ${active ? 'bg-danger animate-pulse' : 'bg-slate-500'}`}
    />
    {active ? 'Live' : 'Paused'}
  </span>
)

export default App
