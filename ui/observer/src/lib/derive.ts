import { AgentProfile, NormalizedBundle, NormalizedDiaryEntry, NormalizedEvent, eventAgentId, safeDate } from './bundle'

export type AgentStatus = 'pending' | 'alive' | 'respawning' | 'expired'

export interface AgentSnapshot {
  agentId: string
  profile: AgentProfile
  status: AgentStatus
  lifeIndex: number
  msLeft: number | null
  timerDurationMs: number | null
  tickSeconds: number | null
  lastDiary?: NormalizedDiaryEntry
  lastChunk?: string
}

export const deriveAgentSnapshots = (bundle: NormalizedBundle, playheadMs: number): Record<string, AgentSnapshot> => {
  const snapshots: Record<string, AgentSnapshot> = {}
  bundle.agentOrder.forEach((agentId) => {
    snapshots[agentId] = {
      agentId,
      profile: bundle.agents[agentId],
      status: 'pending',
      lifeIndex: 0,
      msLeft: null,
      timerDurationMs: null,
      tickSeconds: null,
    }
  })

  for (const event of bundle.events) {
    if (event.tsMs > playheadMs) {
      break
    }
    const agentId = eventAgentId(event)
    if (!agentId) {
      continue
    }
    const snapshot = snapshots[agentId]
    if (!snapshot) {
      continue
    }

    switch (event.event) {
      case 'agent.spawned':
        snapshot.status = 'alive'
        snapshot.lifeIndex = 0
        snapshot.msLeft = null
        break
      case 'timer.started':
        snapshot.status = 'alive'
        snapshot.timerDurationMs = numberOrNull(event.payload.duration_ms)
        snapshot.tickSeconds = numberOrNull(event.payload.tick_seconds)
        snapshot.msLeft = snapshot.timerDurationMs
        break
      case 'timer.tick':
        snapshot.msLeft = numberOrNull(event.payload.ms_left)
        break
      case 'agent.chunk':
        if (typeof event.payload.content === 'string') {
          snapshot.lastChunk = event.payload.content
        }
        break
      case 'agent.diary_entry': {
        const entry = normalizeDiaryFromPayload(event.payload.entry)
        if (entry) {
          snapshot.lastDiary = entry
          snapshot.lifeIndex = entry.life_index
        }
        break
      }
      case 'agent.death':
        snapshot.status = 'expired'
        snapshot.msLeft = 0
        break
      case 'agent.respawn':
        snapshot.status = 'respawning'
        snapshot.lifeIndex = numberOrNull(event.payload.life_index) ?? snapshot.lifeIndex + 1
        snapshot.msLeft = null
        snapshot.timerDurationMs = null
        break
      default:
        break
    }
  }

  return snapshots
}

export interface DiaryLifeGroup {
  lifeIndex: number
  entries: NormalizedDiaryEntry[]
}

export const groupDiariesByLife = (entries: NormalizedDiaryEntry[]): DiaryLifeGroup[] => {
  const groups = new Map<number, NormalizedDiaryEntry[]>()
  entries.forEach((entry) => {
    const list = groups.get(entry.life_index) ?? []
    list.push(entry)
    groups.set(entry.life_index, list)
  })
  return Array.from(groups.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([lifeIndex, list]) => ({
      lifeIndex,
      entries: list.sort((a, b) => a.createdAtMs - b.createdAtMs),
    }))
}

const numberOrNull = (value: unknown): number | null => {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

const normalizeDiaryFromPayload = (value: unknown): NormalizedDiaryEntry | undefined => {
  if (!value || typeof value !== 'object') {
    return undefined
  }
  const entry = value as Partial<NormalizedDiaryEntry>
  if (typeof entry.text !== 'string') {
    return undefined
  }
  return {
    life_index: typeof entry.life_index === 'number' ? entry.life_index : 0,
    tick_ms_left: typeof entry.tick_ms_left === 'number' ? entry.tick_ms_left : 0,
    text: entry.text,
    tags: Array.isArray(entry.tags) ? entry.tags.map(String) : [],
    created_at: typeof entry.created_at === 'string' ? entry.created_at : new Date().toISOString(),
    createdAtMs: entry.createdAtMs ?? safeDate(entry.created_at ?? new Date().toISOString()),
  }
}

export const getAgentEvents = (bundle: NormalizedBundle, agentId: string, type?: string): NormalizedEvent[] => {
  const list = bundle.eventsByAgent[agentId] ?? []
  if (!type) return list
  return list.filter((event) => event.event === type)
}
