import { useCallback, useEffect, useMemo, useState } from 'react'
import { NormalizedBundle } from '@/lib/bundle'
import { usePlayback } from '@/hooks/usePlayback'
import { useLiveConnection, ConnectionStatus } from '@/hooks/useLiveConnection'
import { BundleLoader } from '@/components/BundleLoader'
import { PlaybackBar } from '@/components/PlaybackBar'
import { BoardView } from '@/components/BoardView'
import { formatDuration, formatTimestamp } from '@/lib/time'
import { EventFilters } from '@/components/EventFilters'
import { EventCategory, createDefaultFilterState } from '@/lib/filters'
import { AgentStatusPanel } from '@/components/AgentStatusPanel'
import { LiveEventFeed } from '@/components/LiveEventFeed'
import { LiveDiaryPanel } from '@/components/LiveDiaryPanel'
import { LiveMetricsBar } from '@/components/LiveMetricsBar'

type ViewMode = 'live' | 'replay'

const App = () => {
  const [mode, setMode] = useState<ViewMode>('replay')
  const [bundle, setBundle] = useState<NormalizedBundle | null>(null)
  const timeline = bundle?.timeline ?? { startMs: 0, endMs: 1 }
  const playback = usePlayback(timeline)
  const { seekMs, setSpeed, setPlaying } = playback
  const [filters, setFilters] = useState(createDefaultFilterState)

  // Live connection
  const wsUrl = `ws://localhost:${import.meta.env.VITE_WS_PORT || 8765}`
  const live = useLiveConnection(wsUrl)

  const eventsForView = useMemo(() => {
    if (!bundle) return []
    return bundle.events.filter((event) => event.tsMs <= playback.playheadMs)
  }, [bundle, playback.playheadMs])

  const activeCategories = useMemo(() => {
    const enabled = Object.entries(filters)
      .filter(([, value]) => value)
      .map(([key]) => key as EventCategory)
    return new Set<EventCategory>(enabled)
  }, [filters])

  const handleToggleFilter = useCallback((category: EventCategory) => {
    setFilters((prev) => ({
      ...prev,
      [category]: !prev[category],
    }))
  }, [])

  const handleBundleLoaded = (next: NormalizedBundle) => {
    setBundle(next)
    seekMs(next.timeline.startMs)
    setSpeed(1)
    setMode('replay')
  }

  const handleModeChange = (newMode: ViewMode) => {
    setMode(newMode)
    if (newMode === 'live') {
      live.connect()
    } else {
      live.disconnect()
    }
  }

  useEffect(() => {
    if (!bundle) return
    setPlaying(true)
  }, [bundle, setPlaying])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      live.disconnect()
    }
  }, [])

  const agentCount = Object.keys(live.state.agents).length

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
                {mode === 'live'
                  ? 'Live Dashboard'
                  : bundle?.raw.experiment.slug ?? 'Awaiting emergent council run'}
              </h1>
              <p className="max-w-xl text-sm text-slate-400">
                {mode === 'live'
                  ? 'Connected to a live experiment. Watch agents negotiate in real time.'
                  : bundle?.raw.experiment.description ??
                    'Connect live or drop a recorded JSON bundle to replay.'}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <ModeToggle mode={mode} onModeChange={handleModeChange} status={live.status} />
              {mode === 'replay' && <BundleLoader onLoaded={handleBundleLoaded} />}
            </div>
          </div>

          {mode === 'live' && live.status === 'connected' && agentCount > 0 && (
            <div className="grid gap-3 md:grid-cols-3">
              <Stat
                label="Active Agents"
                value={(agentCount - live.state.metrics.totalDeaths).toString()}
                hint={`${live.state.metrics.totalDeaths} deaths`}
              />
              <Stat
                label="Diary Entries"
                value={live.state.metrics.totalDiaryEntries.toString()}
                hint="total reflections"
              />
              <Stat
                label="Messages"
                value={live.state.metrics.totalMessages.toString()}
                hint={`${live.state.metrics.totalToolCalls} tool calls`}
              />
            </div>
          )}

          {mode === 'replay' && bundle && (
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

        {mode === 'live' ? (
          <LiveView live={live} />
        ) : bundle ? (
          <ReplayView
            bundle={bundle}
            playback={playback}
            eventsForView={eventsForView}
            filters={filters}
            activeCategories={activeCategories}
            onToggleFilter={handleToggleFilter}
          />
        ) : (
          <EmptyState onGoLive={() => handleModeChange('live')} />
        )}
      </div>
    </div>
  )
}

// Mode Toggle Component
interface ModeToggleProps {
  mode: ViewMode
  onModeChange: (mode: ViewMode) => void
  status: ConnectionStatus
}

const ModeToggle = ({ mode, onModeChange, status }: ModeToggleProps) => (
  <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 p-1">
    <button
      type="button"
      onClick={() => onModeChange('replay')}
      className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
        mode === 'replay'
          ? 'bg-white/10 text-white'
          : 'text-slate-400 hover:text-slate-200'
      }`}
    >
      Replay
    </button>
    <button
      type="button"
      onClick={() => onModeChange('live')}
      className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
        mode === 'live'
          ? 'bg-emerald-500/20 text-emerald-300'
          : 'text-slate-400 hover:text-slate-200'
      }`}
    >
      <span
        className={`h-2 w-2 rounded-full ${
          status === 'connected'
            ? 'bg-emerald-500 animate-pulse'
            : status === 'connecting'
              ? 'bg-amber-500 animate-pulse'
              : 'bg-slate-500'
        }`}
      />
      Live
    </button>
  </div>
)

// Live View Component
interface LiveViewProps {
  live: ReturnType<typeof useLiveConnection>
}

const LiveView = ({ live }: LiveViewProps) => {
  const { status, state, error, connect } = live

  if (status === 'disconnected' || status === 'error') {
    return (
      <div className="space-y-4">
        <div className="rounded-3xl border border-dashed border-white/10 bg-white/5 p-10 text-center">
          <p className="text-slate-400">
            {status === 'error' ? (
              <>
                <span className="text-rose-400">Connection failed:</span> {error}
              </>
            ) : (
              'Not connected to a live experiment'
            )}
          </p>
          <button
            type="button"
            onClick={connect}
            className="mt-4 rounded-xl bg-emerald-500/20 px-4 py-2 text-sm font-medium text-emerald-300 transition hover:bg-emerald-500/30"
          >
            Connect to ws://localhost:8765
          </button>
          <p className="mt-4 text-xs text-slate-500">
            Start an experiment with <code>just emergent-live</code>
          </p>
        </div>
      </div>
    )
  }

  if (status === 'connecting') {
    return (
      <div className="rounded-3xl border border-dashed border-amber-500/30 bg-amber-500/5 p-10 text-center">
        <div className="inline-flex items-center gap-2 text-amber-300">
          <span className="h-2 w-2 animate-pulse rounded-full bg-amber-500" />
          Connecting to live experiment...
        </div>
      </div>
    )
  }

  const agentCount = Object.keys(state.agents).length

  if (agentCount === 0 && state.events.length === 0) {
    return (
      <div className="rounded-3xl border border-dashed border-emerald-500/30 bg-emerald-500/5 p-10 text-center">
        <div className="inline-flex items-center gap-2 text-emerald-300">
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
          Connected. Waiting for experiment to start...
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Agents will appear here once spawned
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <LiveMetricsBar metrics={state.metrics} agentCount={agentCount} />

      <AgentStatusPanel agents={state.agents} timers={state.timers} />

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <LiveEventFeed events={state.events} agents={state.agents} />
        </div>
        <div className="lg:col-span-2">
          <LiveDiaryPanel diaries={state.diaries} agents={state.agents} />
        </div>
      </div>
    </div>
  )
}

// Replay View Component
interface ReplayViewProps {
  bundle: NormalizedBundle
  playback: ReturnType<typeof usePlayback>
  eventsForView: NormalizedBundle['events']
  filters: ReturnType<typeof createDefaultFilterState>
  activeCategories: Set<EventCategory>
  onToggleFilter: (category: EventCategory) => void
}

const ReplayView = ({
  bundle,
  playback,
  eventsForView,
  filters,
  activeCategories,
  onToggleFilter,
}: ReplayViewProps) => (
  <>
    <EventFilters filters={filters} onToggle={onToggleFilter} />
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
        active={playback.playing && playback.playheadMs < bundle.timeline.endMs}
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
      events={eventsForView}
      playback={playback}
      activeCategories={activeCategories}
      diaryEnabled={filters.diary}
    />
  </>
)

// Empty State Component
interface EmptyStateProps {
  onGoLive: () => void
}

const EmptyState = ({ onGoLive }: EmptyStateProps) => (
  <div className="rounded-3xl border border-dashed border-white/10 bg-white/5 p-10 text-center text-slate-400">
    <p>
      Run <code>just emergent-run</code> (OpenRouter required) or drop a recorded JSON
      bundle to replay the investigation as it happened.
    </p>
    <div className="mt-6 flex items-center justify-center gap-4">
      <span className="text-slate-500">or</span>
      <button
        type="button"
        onClick={onGoLive}
        className="rounded-xl bg-emerald-500/20 px-4 py-2 text-sm font-medium text-emerald-300 transition hover:bg-emerald-500/30"
      >
        Connect Live
      </button>
    </div>
    <p className="mt-4 text-xs text-slate-500">
      For live mode, start with: <code>just emergent-live</code>
    </p>
  </div>
)

// Stat Component
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
