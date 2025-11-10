import { NormalizedBundle, NormalizedEvent } from '@/lib/bundle'
import { PlaybackControls } from '@/hooks/usePlayback'
import { ChatReplay } from './ChatReplay'
import { DiaryPanel } from './DiaryPanel'
import { EventCategory } from '@/lib/filters'

interface BoardViewProps {
  bundle: NormalizedBundle
  events: NormalizedEvent[]
  playback: PlaybackControls
  activeCategories: Set<EventCategory>
  diaryEnabled: boolean
}

export const BoardView = ({
  bundle,
  events,
  playback,
  activeCategories,
  diaryEnabled,
}: BoardViewProps) => {
  const handleJump = (tsMs: number) => {
    playback.seekMs(tsMs)
    playback.setPlaying(false)
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.7fr)_minmax(280px,1fr)]">
      <ChatReplay
        bundle={bundle}
        events={events}
        playback={playback}
        activeCategories={activeCategories}
        onJump={handleJump}
      />
      {diaryEnabled ? (
        <DiaryPanel bundle={bundle} playback={playback} onJump={handleJump} />
      ) : (
        <div className="rounded-3xl border border-dashed border-white/10 bg-white/5 p-6 text-center text-sm text-slate-500">
          Diary feed hidden — toggle the Diary filter to restore entries.
        </div>
      )}
    </div>
  )
}
