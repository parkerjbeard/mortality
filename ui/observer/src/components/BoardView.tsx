import { NormalizedBundle, NormalizedEvent } from '@/lib/bundle'
import { PlaybackControls } from '@/hooks/usePlayback'
import { ChatReplay } from './ChatReplay'
import { DiaryPanel } from './DiaryPanel'

interface BoardViewProps {
  bundle: NormalizedBundle
  events: NormalizedEvent[]
  playback: PlaybackControls
}

export const BoardView = ({ bundle, events, playback }: BoardViewProps) => {
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
        onJump={handleJump}
      />
      <DiaryPanel bundle={bundle} playback={playback} onJump={handleJump} />
    </div>
  )
}
