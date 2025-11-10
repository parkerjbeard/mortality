import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react'
import clsx from 'clsx'
import { NormalizedBundle, NormalizedEvent } from '@/lib/bundle'
import { getAgentDisplayName, getAgentInitials } from '@/lib/agents'
import { PlaybackControls } from '@/hooks/usePlayback'
import { formatCountdown, formatTimestamp } from '@/lib/time'
import { MarkdownContent } from './MarkdownContent'

interface ChatReplayProps {
  bundle: NormalizedBundle
  events: NormalizedEvent[]
  playback: PlaybackControls
  onJump: (tsMs: number) => void
}

interface ChatMessage {
  id: string
  tsMs: number
  agentId: string
  direction: string
  role: string
  content: string
  tickMsLeft?: number
}

const palette = [
  {
    avatar: 'border-emerald-500/50 bg-emerald-500/10 text-emerald-100',
    bubble: 'border-emerald-500/30 bg-emerald-500/10',
  },
  {
    avatar: 'border-sky-500/50 bg-sky-500/10 text-sky-100',
    bubble: 'border-sky-500/30 bg-sky-500/10',
  },
  {
    avatar: 'border-purple-500/50 bg-purple-500/10 text-purple-100',
    bubble: 'border-purple-500/30 bg-purple-500/10',
  },
  {
    avatar: 'border-amber-500/50 bg-amber-500/10 text-amber-100',
    bubble: 'border-amber-500/30 bg-amber-500/10',
  },
  {
    avatar: 'border-rose-500/50 bg-rose-500/10 text-rose-100',
    bubble: 'border-rose-500/30 bg-rose-500/10',
  },
]

export const ChatReplay = ({
  bundle,
  events,
  playback,
  onJump,
}: ChatReplayProps) => {
  const messages = useMemo(() => collectMessages(events), [events])
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const copyTimeoutRef = useRef<number | undefined>()

  const handleCopy = useCallback(async (message: ChatMessage) => {
    try {
      await copyText(message.content)
      setCopiedId(message.id)
      if (copyTimeoutRef.current) {
        window.clearTimeout(copyTimeoutRef.current)
      }
      copyTimeoutRef.current = window.setTimeout(() => setCopiedId(null), 1800)
    } catch (error) {
      console.error('Failed to copy chat message', error)
    }
  }, [])

  const handleKeyActivate = useCallback(
    (event: KeyboardEvent<HTMLDivElement>, tsMs: number) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        onJump(tsMs)
      }
    },
    [onJump],
  )

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) {
        window.clearTimeout(copyTimeoutRef.current)
      }
    }
  }, [])

  return (
    <section className="flex flex-col rounded-3xl border border-white/5 bg-panel/60 p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
            Chat replay
          </p>
          <p className="text-sm text-slate-300">
            Observing council dialogue until{' '}
            <span className="text-white">
              {formatTimestamp(playback.playheadMs)}
            </span>
          </p>
        </div>
        <span className="text-xs text-slate-500">
          {messages.length} message{messages.length === 1 ? '' : 's'}
        </span>
      </div>
      <div className="mt-4 flex flex-1 flex-col rounded-2xl border border-white/5 bg-black/20">
        <ul className="max-h-[70vh] flex-1 space-y-4 overflow-y-auto p-4 pr-3">
          {messages.map((message) => {
            const tone = palette[getToneIndex(bundle, message.agentId)]
            const profile = bundle.agents[message.agentId]
            const name = getAgentDisplayName(profile, message.agentId)
            const initials = getAgentInitials(profile, message.agentId)
            const countdownLabel =
              typeof message.tickMsLeft === 'number'
                ? `${formatCountdown(message.tickMsLeft)} left`
                : null
            const copyLabel = copiedId === message.id ? 'Copied' : 'Copy'
            return (
              <li key={message.id}>
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => onJump(message.tsMs)}
                  onKeyDown={(event) => handleKeyActivate(event, message.tsMs)}
                  className={clsx(
                    'group flex w-full gap-3 rounded-2xl border border-white/5 bg-white/5 p-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
                    message.direction === 'outbound'
                      ? 'flex-row-reverse hover:translate-x-1'
                      : 'hover:-translate-x-1',
                  )}
                >
                  <span
                    className={clsx(
                      'inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border text-xs font-semibold uppercase tracking-wide',
                      tone.avatar,
                    )}
                  >
                    {initials}
                  </span>
                  <div
                    className={clsx(
                      'flex w-full max-w-xl flex-col gap-2',
                      message.direction === 'outbound'
                        ? 'items-end text-right'
                        : 'items-start text-left',
                    )}
                  >
                    <div className="flex w-full flex-wrap items-center gap-2 text-[11px] uppercase tracking-wide text-slate-500">
                      <span className="font-semibold text-slate-300">
                        {name}
                      </span>
                      {message.role && (
                        <span className="rounded-full bg-white/5 px-2 py-0.5">
                          {message.role}
                        </span>
                      )}
                      <span>{message.direction}</span>
                      <span>{formatTimestamp(message.tsMs)}</span>
                      {countdownLabel && (
                        <span className="rounded-full bg-white/5 px-2 py-0.5 text-slate-300">
                          {countdownLabel}
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation()
                          handleCopy(message)
                        }}
                        className={clsx(
                          'ml-auto rounded-full border border-white/10 bg-black/20 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-slate-200 transition hover:border-white/40 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
                          copiedId === message.id &&
                            'border-accent/40 bg-accent/10 text-accent',
                        )}
                      >
                        {copyLabel}
                      </button>
                    </div>
                    <div
                      className={clsx(
                        'w-full rounded-2xl border px-4 py-3 shadow-inner',
                        tone.bubble,
                        message.direction === 'outbound'
                          ? 'rounded-tr-sm'
                          : 'rounded-tl-sm',
                      )}
                    >
                      <MarkdownContent content={message.content} />
                    </div>
                  </div>
                </div>
              </li>
            )
          })}
          {messages.length === 0 && (
            <li className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-6 text-center text-sm text-slate-500">
              Press play or scrub the timeline to watch the conversation unfold.
            </li>
          )}
        </ul>
      </div>
    </section>
  )
}

const collectMessages = (events: NormalizedEvent[]): ChatMessage[] => {
  return events
    .filter((event) => event.event === 'agent.message')
    .map((event): ChatMessage | null => {
      const payload = event.payload as Record<string, unknown>
      const agentId = extractAgentId(payload)
      if (!agentId) {
        return null
      }
      const messagePayload = payload['message'] as
        | { role?: unknown; content?: unknown }
        | undefined
      const directionValue = payload['direction']
      const direction =
        typeof directionValue === 'string' ? directionValue : 'outbound'
      const role =
        typeof messagePayload?.role === 'string' ? messagePayload.role : ''
      const content = normalizeContent(messagePayload?.content)
      if (!content.trim()) {
        return null
      }
      return {
        id: `msg-${event.seq}`,
        tsMs: event.tsMs,
        agentId,
        direction,
        role,
        content,
        tickMsLeft: extractTickMsLeft(payload),
      }
    })
    .filter((entry): entry is ChatMessage => entry !== null)
    .sort((a, b) => a.tsMs - b.tsMs)
}

const normalizeContent = (value: unknown): string => {
  if (typeof value === 'string') {
    return value
  }
  if (Array.isArray(value)) {
    return value
      .map((chunk) => flattenContentChunk(chunk))
      .filter((chunk) => chunk.length > 0)
      .join('\n\n')
  }
  if (value && typeof value === 'object') {
    const direct = (value as { text?: unknown; content?: unknown }).text
    if (typeof direct === 'string') {
      return direct
    }
    const nested = (value as { content?: unknown }).content
    if (typeof nested === 'string') {
      return nested
    }
    if (Array.isArray(nested)) {
      return nested
        .map((chunk) => flattenContentChunk(chunk))
        .filter((chunk) => chunk.length > 0)
        .join('\n\n')
    }
    return safeStringify(value)
  }
  return ''
}

const flattenContentChunk = (chunk: unknown): string => {
  if (typeof chunk === 'string') {
    return chunk
  }
  if (!chunk || typeof chunk !== 'object') {
    return typeof chunk === 'undefined' ? '' : safeStringify(chunk)
  }
  const record = chunk as Record<string, unknown>
  if (typeof record.text === 'string') {
    return record.text
  }
  if (typeof record.content === 'string') {
    return record.content
  }
  if (Array.isArray(record.content)) {
    return record.content
      .map((item) => flattenContentChunk(item))
      .filter((value) => value.length > 0)
      .join('\n\n')
  }
  return safeStringify(chunk)
}

const safeStringify = (value: unknown): string => {
  try {
    return JSON.stringify(value)
  } catch (error) {
    console.error('Failed to stringify interaction content', error)
    return ''
  }
}

const getToneIndex = (bundle: NormalizedBundle, agentId: string): number => {
  const index = bundle.agentOrder.indexOf(agentId)
  if (index === -1) {
    return 0
  }
  return index % palette.length
}

const extractTickMsLeft = (
  payload: Record<string, unknown>,
): number | undefined => {
  const tick = payload['tick_ms_left']
  if (typeof tick === 'number' && Number.isFinite(tick)) {
    return tick
  }
  const msLeft = payload['ms_left']
  if (typeof msLeft === 'number' && Number.isFinite(msLeft)) {
    return msLeft
  }
  return undefined
}

const extractAgentId = (payload: Record<string, unknown>): string => {
  const direct = payload['agent_id']
  if (typeof direct === 'string') {
    return direct
  }
  if (typeof direct === 'number') {
    return String(direct)
  }
  const nested = payload['profile'] as { agent_id?: string } | undefined
  if (nested?.agent_id) {
    return nested.agent_id
  }
  return ''
}

const copyText = async (text: string) => {
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch (error) {
      console.warn('Clipboard API failed, attempting fallback', error)
    }
  }
  fallbackCopy(text)
}

const fallbackCopy = (text: string) => {
  if (typeof document === 'undefined') {
    throw new Error('Clipboard unavailable in this environment')
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'absolute'
  textarea.style.left = '-9999px'
  textarea.style.top = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()
  const success = document.execCommand('copy')
  document.body.removeChild(textarea)
  if (!success) {
    throw new Error('Fallback clipboard copy failed')
  }
}
