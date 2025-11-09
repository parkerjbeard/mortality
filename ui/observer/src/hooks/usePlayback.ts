import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

interface PlaybackRange {
  startMs: number
  endMs: number
}

export interface PlaybackControls {
  playheadMs: number
  playing: boolean
  progress: number
  durationMs: number
  speed: number
  setSpeed: (value: number) => void
  setPlaying: (value: boolean) => void
  seekFraction: (value: number) => void
  seekMs: (value: number) => void
  toggle: () => void
}

export const usePlayback = ({ startMs, endMs }: PlaybackRange): PlaybackControls => {
  const durationMs = Math.max(1, endMs - startMs)
  const [playheadMs, setPlayheadMs] = useState(startMs)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const rafRef = useRef<number>()
  const lastTick = useRef<number>()

  useEffect(() => {
    setPlayheadMs(startMs)
    setPlaying(false)
  }, [startMs, endMs])

  useEffect(() => {
    if (!playing) {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
      }
      lastTick.current = undefined
      return
    }

    const step = (now: number) => {
      if (lastTick.current === undefined) {
        lastTick.current = now
      }
      const delta = now - (lastTick.current ?? now)
      lastTick.current = now
      let reachedEnd = false
      setPlayheadMs((current) => {
        const next = Math.min(endMs, current + delta * speed)
        if (next >= endMs) {
          reachedEnd = true
        }
        return next
      })
      if (reachedEnd) {
        setPlaying(false)
        lastTick.current = undefined
        return
      }
      rafRef.current = requestAnimationFrame(step)
    }

    rafRef.current = requestAnimationFrame(step)
    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
      }
      lastTick.current = undefined
    }
  }, [playing, speed, endMs])

  const seekMs = useCallback(
    (value: number) => {
      const clamped = Math.min(endMs, Math.max(startMs, value))
      setPlayheadMs(clamped)
    },
    [startMs, endMs],
  )

  const seekFraction = useCallback(
    (fraction: number) => {
      const clamped = Math.min(1, Math.max(0, fraction))
      seekMs(startMs + durationMs * clamped)
    },
    [durationMs, seekMs, startMs],
  )

  const toggle = useCallback(() => setPlaying((prev) => !prev), [])

  const progress = useMemo(() => (playheadMs - startMs) / durationMs, [durationMs, playheadMs, startMs])

  return {
    playheadMs,
    playing,
    progress,
    durationMs,
    speed,
    setSpeed,
    setPlaying,
    seekFraction,
    seekMs,
    toggle,
  }
}
