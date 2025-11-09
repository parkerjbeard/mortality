import { PlaybackControls } from '@/hooks/usePlayback'
import { NormalizedBundle } from '@/lib/bundle'
import { formatCountdown, formatDuration, formatTimestamp } from '@/lib/time'
import clsx from 'clsx'

interface PlaybackBarProps {
  playback: PlaybackControls
  bundle: NormalizedBundle
}

const speedOptions = [0.5, 1, 2, 4]

export const PlaybackBar = ({ playback, bundle }: PlaybackBarProps) => {
  return (
    <div className="rounded-2xl border border-white/5 bg-panel/80 p-4 shadow-2xl shadow-black/30 backdrop-blur">
      <div className="flex flex-wrap items-center gap-4">
        <button
          type="button"
          className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-lg font-semibold text-white transition hover:bg-white/20"
          onClick={playback.toggle}
          aria-label={playback.playing ? 'Pause playback' : 'Play timeline'}
        >
          {playback.playing ? '❚❚' : '►'}
        </button>
        <div className="flex flex-col">
          <span className="text-xs uppercase tracking-wide text-slate-400">Now</span>
          <span className="font-semibold text-white">{formatTimestamp(playback.playheadMs)}</span>
        </div>
        <div className="flex flex-col">
          <span className="text-xs uppercase tracking-wide text-slate-400">Countdown</span>
          <span className="font-semibold text-white">{formatCountdown(bundle.timeline.endMs - playback.playheadMs)}</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-slate-500">Speed</span>
          {speedOptions.map((speed) => (
            <button
              key={speed}
              type="button"
              onClick={() => playback.setSpeed(speed)}
              className={clsx(
                'rounded-full px-3 py-1 text-xs font-semibold transition',
                playback.speed === speed ? 'bg-accent/30 text-accent' : 'bg-white/5 text-slate-400 hover:bg-white/10',
              )}
            >
              {speed.toFixed(speed < 1 ? 1 : 0)}×
            </button>
          ))}
        </div>
      </div>
      <div className="mt-4 space-y-1">
        <input
          type="range"
          min={0}
          max={1000}
          value={Math.round(playback.progress * 1000)}
          onChange={(event) => playback.seekFraction(Number(event.target.value) / 1000)}
          className="w-full accent-accent"
        />
        <div className="flex justify-between text-xs text-slate-400">
          <span>{formatTimestamp(bundle.timeline.startMs)}</span>
          <span>{formatDuration(bundle.timeline.durationMs)}</span>
          <span>{formatTimestamp(bundle.timeline.endMs)}</span>
        </div>
      </div>
    </div>
  )
}
