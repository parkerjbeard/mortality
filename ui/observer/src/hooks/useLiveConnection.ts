import { useCallback, useEffect, useRef, useState } from 'react'
import { AgentProfile, NormalizedDiaryEntry, NormalizedEvent, safeDate } from '@/lib/bundle'

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error'

export interface AgentTimer {
  duration_ms: number
  tick_seconds: number
  started_at: string
  ms_left: number
  status: 'active' | 'expired' | 'dead'
}

export interface LiveMetrics {
  totalMessages: number
  totalDiaryEntries: number
  totalBroadcasts: number
  totalToolCalls: number
  totalDeaths: number
  messagesPerAgent: Record<string, number>
  diaryEntriesPerAgent: Record<string, number>
  startTime: number | null
  elapsedMs: number
}

export interface LiveState {
  agents: Record<string, AgentProfile & { session?: { provider: string; model: string } }>
  timers: Record<string, AgentTimer>
  events: NormalizedEvent[]
  diaries: Record<string, NormalizedDiaryEntry[]>
  metrics: LiveMetrics
}

export interface LiveConnection {
  status: ConnectionStatus
  state: LiveState
  connect: () => void
  disconnect: () => void
  error: string | null
}

const DEFAULT_METRICS: LiveMetrics = {
  totalMessages: 0,
  totalDiaryEntries: 0,
  totalBroadcasts: 0,
  totalToolCalls: 0,
  totalDeaths: 0,
  messagesPerAgent: {},
  diaryEntriesPerAgent: {},
  startTime: null,
  elapsedMs: 0,
}

const DEFAULT_STATE: LiveState = {
  agents: {},
  timers: {},
  events: [],
  diaries: {},
  metrics: { ...DEFAULT_METRICS },
}

export const useLiveConnection = (
  url: string = 'ws://localhost:8765',
  options?: {
    maxEvents?: number
    reconnectDelay?: number
    maxReconnectAttempts?: number
  }
): LiveConnection => {
  const { maxEvents = 1000, reconnectDelay = 2000, maxReconnectAttempts = 5 } = options ?? {}

  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const [state, setState] = useState<LiveState>(DEFAULT_STATE)
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const startTimeRef = useRef<number | null>(null)

  // Update elapsed time
  useEffect(() => {
    if (status !== 'connected' || !startTimeRef.current) return

    const interval = setInterval(() => {
      setState((prev) => ({
        ...prev,
        metrics: {
          ...prev.metrics,
          elapsedMs: Date.now() - (startTimeRef.current ?? Date.now()),
        },
      }))
    }, 1000)

    return () => clearInterval(interval)
  }, [status])

  const processEvent = useCallback(
    (event: NormalizedEvent) => {
      setState((prev) => {
        const newEvents = [...prev.events, event].slice(-maxEvents)
        const newMetrics = { ...prev.metrics }
        const newDiaries = { ...prev.diaries }
        const newTimers = { ...prev.timers }
        const newAgents = { ...prev.agents }
        const agentId = event.payload.agent_id as string | undefined

        // Update metrics based on event type
        switch (event.event) {
          case 'agent.spawned': {
            const profile = event.payload.profile as
              | (AgentProfile & { session?: { provider: string; model: string } })
              | undefined
            if (profile?.agent_id) {
              const session = event.payload.session as { provider: string; model: string } | undefined
              newAgents[profile.agent_id] = session ? { ...profile, session } : { ...profile }
            }
            break
          }

          case 'agent.message':
            newMetrics.totalMessages++
            if (agentId) {
              newMetrics.messagesPerAgent[agentId] =
                (newMetrics.messagesPerAgent[agentId] ?? 0) + 1
            }
            break

          case 'agent.diary_entry': {
            newMetrics.totalDiaryEntries++
            if (agentId) {
              newMetrics.diaryEntriesPerAgent[agentId] =
                (newMetrics.diaryEntriesPerAgent[agentId] ?? 0) + 1

              // Add to diaries
              const entry = event.payload.entry as {
                life_index?: number
                entry_index?: number
                tick_ms_left?: number
                text?: string
                tags?: string[]
                created_at?: string
              }
              if (entry) {
                const normalizedEntry: NormalizedDiaryEntry = {
                  life_index: entry.life_index ?? 0,
                  entry_index: entry.entry_index ?? 0,
                  tick_ms_left: entry.tick_ms_left ?? 0,
                  text: entry.text ?? '',
                  tags: entry.tags ?? [],
                  created_at: entry.created_at ?? new Date().toISOString(),
                  createdAtMs: safeDate(entry.created_at ?? new Date().toISOString()),
                }
                if (!newDiaries[agentId]) {
                  newDiaries[agentId] = []
                }
                newDiaries[agentId] = [...newDiaries[agentId], normalizedEntry]
              }
            }
            break
          }

          case 'agent.broadcast':
            newMetrics.totalBroadcasts++
            break

          case 'agent.tool_call':
            newMetrics.totalToolCalls++
            break

          case 'agent.death':
            newMetrics.totalDeaths++
            if (agentId && newTimers[agentId]) {
              newTimers[agentId] = { ...newTimers[agentId], status: 'dead' }
            }
            break

          case 'timer.started':
            if (agentId) {
              const durationMs = (event.payload.duration_ms as number) ?? 0
              const tickSeconds = (event.payload.tick_seconds as number) ?? 0
              const startedAt = (event.payload.started_at as string) ?? new Date().toISOString()
              newTimers[agentId] = {
                duration_ms: durationMs,
                tick_seconds: tickSeconds,
                started_at: startedAt,
                ms_left: durationMs,
                status: 'active',
              }
            }
            break

          case 'timer.tick':
            if (agentId && newTimers[agentId]) {
              newTimers[agentId] = {
                ...newTimers[agentId],
                ms_left: (event.payload.ms_left as number) ?? 0,
              }
            }
            break

          case 'timer.expired':
            if (agentId && newTimers[agentId]) {
              newTimers[agentId] = { ...newTimers[agentId], status: 'expired', ms_left: 0 }
            }
            break
        }

        return {
          ...prev,
          events: newEvents,
          metrics: newMetrics,
          diaries: newDiaries,
          timers: newTimers,
          agents: newAgents,
        }
      })
    },
    [maxEvents]
  )

  const handleMessage = useCallback(
    (messageEvent: MessageEvent) => {
      try {
        const data = JSON.parse(messageEvent.data)

        if (data.type === 'initial_state') {
          // Process initial state snapshot
          const agents = data.agents ?? {}
          const timers = data.timers ?? {}
          const recentEvents = (data.recent_events ?? []).map(
            (e: { seq: number; event: string; ts: string; payload: Record<string, unknown> }) => ({
              ...e,
              tsMs: safeDate(e.ts),
            })
          )

          // Find start time from first event
          if (recentEvents.length > 0) {
            startTimeRef.current = Math.min(...recentEvents.map((e: NormalizedEvent) => e.tsMs))
          } else {
            startTimeRef.current = Date.now()
          }

          // Process existing diary entries from events
          const diaries: Record<string, NormalizedDiaryEntry[]> = {}
          const metrics: LiveMetrics = { ...DEFAULT_METRICS, startTime: startTimeRef.current }

          for (const event of recentEvents) {
            const agentId = event.payload.agent_id as string | undefined

            switch (event.event) {
              case 'agent.message':
                metrics.totalMessages++
                if (agentId) {
                  metrics.messagesPerAgent[agentId] =
                    (metrics.messagesPerAgent[agentId] ?? 0) + 1
                }
                break

              case 'agent.diary_entry': {
                metrics.totalDiaryEntries++
                if (agentId) {
                  metrics.diaryEntriesPerAgent[agentId] =
                    (metrics.diaryEntriesPerAgent[agentId] ?? 0) + 1

                  const entry = event.payload.entry as {
                    life_index?: number
                    entry_index?: number
                    tick_ms_left?: number
                    text?: string
                    tags?: string[]
                    created_at?: string
                  }
                  if (entry) {
                    const normalizedEntry: NormalizedDiaryEntry = {
                      life_index: entry.life_index ?? 0,
                      entry_index: entry.entry_index ?? 0,
                      tick_ms_left: entry.tick_ms_left ?? 0,
                      text: entry.text ?? '',
                      tags: entry.tags ?? [],
                      created_at: entry.created_at ?? new Date().toISOString(),
                      createdAtMs: safeDate(entry.created_at ?? new Date().toISOString()),
                    }
                    if (!diaries[agentId]) {
                      diaries[agentId] = []
                    }
                    diaries[agentId].push(normalizedEntry)
                  }
                }
                break
              }

              case 'agent.broadcast':
                metrics.totalBroadcasts++
                break

              case 'agent.tool_call':
                metrics.totalToolCalls++
                break

              case 'agent.death':
                metrics.totalDeaths++
                break
            }
          }

          metrics.elapsedMs = Date.now() - (startTimeRef.current ?? Date.now())

          setState({
            agents,
            timers,
            events: recentEvents,
            diaries,
            metrics,
          })
        } else if (data.type === 'event') {
          // Process individual event
          const normalizedEvent: NormalizedEvent = {
            seq: data.seq,
            event: data.event,
            ts: data.ts,
            payload: data.payload,
            tsMs: safeDate(data.ts),
          }
          processEvent(normalizedEvent)
        } else if (data.type === 'pong') {
          // Heartbeat response, ignore
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err)
      }
    },
    [processEvent]
  )

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    setStatus('connecting')
    setError(null)

    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setStatus('connected')
        setError(null)
        reconnectAttemptsRef.current = 0
      }

      ws.onmessage = handleMessage

      ws.onerror = () => {
        setError('WebSocket connection error')
      }

      ws.onclose = (event) => {
        wsRef.current = null

        if (event.wasClean) {
          setStatus('disconnected')
        } else {
          setStatus('error')
          setError(`Connection closed unexpectedly (code: ${event.code})`)

          // Attempt reconnection
          if (reconnectAttemptsRef.current < maxReconnectAttempts) {
            reconnectAttemptsRef.current++
            const delay = reconnectDelay * Math.pow(2, reconnectAttemptsRef.current - 1)
            reconnectTimeoutRef.current = window.setTimeout(() => {
              connect()
            }, delay)
          }
        }
      }
    } catch (err) {
      setStatus('error')
      setError(err instanceof Error ? err.message : 'Failed to connect')
    }
  }, [url, handleMessage, maxReconnectAttempts, reconnectDelay])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    reconnectAttemptsRef.current = maxReconnectAttempts // Prevent reconnection

    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnected')
      wsRef.current = null
    }

    setStatus('disconnected')
    setState(DEFAULT_STATE)
  }, [maxReconnectAttempts])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted')
      }
    }
  }, [])

  return {
    status,
    state,
    connect,
    disconnect,
    error,
  }
}
