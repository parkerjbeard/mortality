import { z } from 'zod'

const diaryEntrySchema = z.object({
  life_index: z.number(),
  entry_index: z.number().int().nonnegative().optional().default(0),
  tick_ms_left: z.number(),
  text: z.string(),
  tags: z.array(z.string()),
  created_at: z.string(),
})

const agentSchema = z.object({
  agent_id: z.string(),
  display_name: z.string(),
  archetype: z.string(),
  summary: z.string(),
  goals: z.array(z.string()).optional().default([]),
  traits: z.array(z.string()).optional().default([]),
})

const eventSchema = z.object({
  seq: z.number(),
  event: z.string(),
  ts: z.string(),
  payload: z.record(z.any()),
})

const bundleSchema = z.object({
  bundle_type: z.string(),
  schema_version: z.number(),
  exported_at: z.string(),
  experiment: z.object({
    slug: z.string(),
    description: z.string().optional().default(''),
  }),
  config: z.record(z.any()),
  llm: z.record(z.any()),
  agents: z.record(agentSchema),
  metadata: z.record(z.any()),
  diaries: z.record(z.array(diaryEntrySchema)),
  events: z.array(eventSchema),
  extra: z.record(z.any()).optional().default({}),
})

export type RawBundle = z.infer<typeof bundleSchema>
export type AgentProfile = z.infer<typeof agentSchema>
export type RawDiaryEntry = z.infer<typeof diaryEntrySchema>

export interface NormalizedDiaryEntry extends RawDiaryEntry {
  createdAtMs: number
}

export interface NormalizedEvent extends z.infer<typeof eventSchema> {
  tsMs: number
}

export interface AgentSessionInfo {
  provider?: string
  model?: string
}

export interface AgentRouteInfo {
  last?: string
  history: string[]
}

export type AgentModelSource = 'routed' | 'session' | 'default'

export interface AgentModelDetails {
  label: string
  source: AgentModelSource
  provider?: string
  history: string[]
}

export interface DiaryConnector {
  fromAgentId: string
  toAgentId: string
  fromTs: number
  toTs: number
}

export interface NormalizedBundle {
  raw: RawBundle
  events: NormalizedEvent[]
  eventsByAgent: Record<string, NormalizedEvent[]>
  diaries: Record<string, NormalizedDiaryEntry[]>
  agents: Record<string, AgentProfile>
  agentOrder: string[]
  agentSessions: Record<string, AgentSessionInfo>
  agentRoutes: Record<string, AgentRouteInfo>
  timeline: {
    startMs: number
    endMs: number
    durationMs: number
  }
  connectors: DiaryConnector[]
}

export const parseBundle = (input: string | object): NormalizedBundle => {
  const parsed =
    typeof input === 'string'
      ? bundleSchema.parse(JSON.parse(input))
      : bundleSchema.parse(input)
  return normalizeBundle(parsed)
}

const normalizeBundle = (raw: RawBundle): NormalizedBundle => {
  const diaries: Record<string, NormalizedDiaryEntry[]> = {}
  Object.entries(raw.diaries).forEach(([agentId, entries]) => {
    diaries[agentId] = entries.map((entry) => ({
      ...entry,
      createdAtMs: safeDate(entry.created_at),
    }))
  })

  const events: NormalizedEvent[] = raw.events
    .map((event) => ({
      ...event,
      tsMs: safeDate(event.ts),
    }))
    .sort((a, b) => {
      if (a.tsMs === b.tsMs) {
        return a.seq - b.seq
      }
      return a.tsMs - b.tsMs
    })

  const allTs = [
    ...events.map((event) => event.tsMs),
    ...Object.values(diaries)
      .flat()
      .map((entry) => entry.createdAtMs),
  ].filter((value) => Number.isFinite(value))

  const defaultTs = Date.now()
  const startMs = allTs.length ? Math.min(...allTs) : defaultTs
  const endMs = allTs.length ? Math.max(...allTs) : startMs + 1
  const durationMs = Math.max(1, endMs - startMs)

  const agentOrder = Object.keys(raw.agents).sort()
  const eventsByAgent: Record<string, NormalizedEvent[]> = {}
  events.forEach((event) => {
    const agentId = eventAgentId(event)
    if (!agentId) {
      return
    }
    if (!eventsByAgent[agentId]) {
      eventsByAgent[agentId] = []
    }
    eventsByAgent[agentId].push(event)
  })

  const agentSessions = extractAgentSessions(events)
  const agentRoutes = extractAgentRoutes(raw, events)
  const connectors = buildDiaryConnectors(events, diaries)

  return {
    raw,
    events,
    eventsByAgent,
    diaries,
    agents: raw.agents,
    agentOrder,
    agentSessions,
    agentRoutes,
    timeline: { startMs, endMs, durationMs },
    connectors,
  }
}

const buildDiaryConnectors = (
  events: NormalizedEvent[],
  diaries: Record<string, NormalizedDiaryEntry[]>,
): DiaryConnector[] => {
  const deaths = events.filter(
    (event) => event.event === 'agent.death' && event.payload.agent_id,
  )
  const diaryList = Object.entries(diaries).flatMap(([agentId, entries]) =>
    entries.map((entry) => ({ ...entry, agentId })),
  )
  const windowMs = 20_000
  const connectors: DiaryConnector[] = []

  deaths.forEach((death) => {
    const fromAgentId = String(death.payload.agent_id)
    const matches = diaryList
      .filter(
        (entry) =>
          entry.agentId !== fromAgentId &&
          entry.createdAtMs >= death.tsMs &&
          entry.createdAtMs <= death.tsMs + windowMs,
      )
      .sort((a, b) => a.createdAtMs - b.createdAtMs)
      .slice(0, 3)

    matches.forEach((match) => {
      connectors.push({
        fromAgentId,
        toAgentId: match.agentId,
        fromTs: death.tsMs,
        toTs: match.createdAtMs,
      })
    })
  })

  return connectors
}

const normalizeIsoTimestamp = (value: string): string => {
  if (typeof value !== 'string') {
    return ''
  }
  let trimmed = value.trim()
  if (!trimmed) {
    return ''
  }
  // Safari struggles with space-separated timestamps; prefer ISO T separator.
  trimmed = trimmed.replace(' ', 'T')
  // Collapse timezone offsets like +00:00 into +0000 for broader compatibility.
  trimmed = trimmed.replace(/([+-]\d{2}):(\d{2})$/, '$1$2')
  // Limit fractional seconds to milliseconds to avoid precision parsing issues.
  trimmed = trimmed.replace(/(\.\d{3})\d+/, '$1')
  // Normalize trailing z to uppercase Z.
  trimmed = trimmed.replace(/z$/, 'Z')
  // Ensure a timezone designation exists; default to Z (UTC).
  if (!/([zZ]|[+-]\d{4})$/.test(trimmed)) {
    trimmed += 'Z'
  }
  return trimmed
}

export const safeDate = (value: string): number => {
  const direct = Date.parse(value)
  if (Number.isFinite(direct)) {
    return direct
  }
  const normalized = normalizeIsoTimestamp(value)
  const fallback = Date.parse(normalized)
  return Number.isFinite(fallback) ? fallback : Date.now()
}

export const eventAgentId = (event: NormalizedEvent): string | undefined => {
  const direct = event.payload.agent_id
  if (typeof direct === 'string') {
    return direct
  }
  if (typeof direct === 'number') {
    return String(direct)
  }
  const nested = (event.payload.profile as { agent_id?: string } | undefined)
    ?.agent_id
  if (nested) {
    return nested
  }
  return undefined
}

const extractAgentSessions = (
  events: NormalizedEvent[],
): Record<string, AgentSessionInfo> => {
  const sessions: Record<string, AgentSessionInfo> = {}
  events.forEach((event) => {
    if (event.event !== 'agent.spawned') {
      return
    }
    const agentId = eventAgentId(event)
    if (!agentId) {
      return
    }
    const sessionInfo = normalizeSessionInfo(event.payload?.session)
    if (sessionInfo) {
      sessions[agentId] = sessionInfo
    }
  })
  return sessions
}

const normalizeSessionInfo = (value: unknown): AgentSessionInfo | undefined => {
  if (!value || typeof value !== 'object') {
    return undefined
  }
  const input = value as Partial<AgentSessionInfo>
  const provider =
    typeof input.provider === 'string' ? input.provider.trim() : undefined
  const model = typeof input.model === 'string' ? input.model.trim() : undefined
  if (!provider && !model) {
    return undefined
  }
  return { provider, model }
}

const extractAgentRoutes = (
  raw: RawBundle,
  events: NormalizedEvent[],
): Record<string, AgentRouteInfo> => {
  const telemetryRoutes = buildRouteHistoryFromEvents(events)
  const metadataRoutes = normalizeMetadataRoutes(raw.metadata)
  return mergeAgentRoutes(telemetryRoutes, metadataRoutes)
}

const buildRouteHistoryFromEvents = (
  events: NormalizedEvent[],
): Record<string, AgentRouteInfo> => {
  const routes: Record<string, AgentRouteInfo> = {}
  events.forEach((event) => {
    if (event.event !== 'agent.route_update') {
      return
    }
    const agentId = eventAgentId(event)
    if (!agentId) {
      return
    }
    const payload = event.payload || {}
    const model =
      typeof payload['model'] === 'string' ? payload['model'].trim() : ''
    const history = collectStringList(payload['history'])
    const existing = routes[agentId] || { history: [] }
    let mergedHistory = existing.history
    if (history.length) {
      mergedHistory = uniqueStrings([...mergedHistory, ...history])
    }
    if (model) {
      mergedHistory = uniqueStrings([...mergedHistory, model])
    }
    routes[agentId] = {
      history: mergedHistory,
      last: model || existing.last || history[history.length - 1],
    }
  })
  return routes
}

const normalizeMetadataRoutes = (
  metadata: Record<string, unknown>,
): Record<string, AgentRouteInfo> => {
  if (!isRecord(metadata)) {
    return {}
  }
  const routed = metadata['routed_models']
  if (!isRecord(routed)) {
    return {}
  }
  const routes: Record<string, AgentRouteInfo> = {}
  Object.entries(routed).forEach(([agentId, value]) => {
    if (!isRecord(value)) {
      return
    }
    const history = collectStringList(value['history'])
    const last = typeof value['last'] === 'string' ? value['last'].trim() : ''
    if (!history.length && !last) {
      return
    }
    const normalizedHistory = history.length
      ? uniqueStrings(history)
      : last
        ? [last]
        : []
    routes[agentId] = {
      history: normalizedHistory,
      last: last || normalizedHistory[normalizedHistory.length - 1],
    }
  })
  return routes
}

const mergeAgentRoutes = (
  base: Record<string, AgentRouteInfo>,
  overrides: Record<string, AgentRouteInfo>,
): Record<string, AgentRouteInfo> => {
  const merged: Record<string, AgentRouteInfo> = {}
  Object.entries(base).forEach(([agentId, info]) => {
    merged[agentId] = {
      history: info.history ? [...info.history] : [],
      last: info.last,
    }
  })
  Object.entries(overrides).forEach(([agentId, info]) => {
    const existing = merged[agentId]
    if (!existing) {
      merged[agentId] = {
        history: info.history ? [...info.history] : [],
        last: info.last,
      }
      return
    }
    const history = uniqueStrings([...existing.history, ...info.history])
    merged[agentId] = {
      history,
      last: info.last || existing.last || history[history.length - 1],
    }
  })
  return merged
}

const extractRoutedModel = (
  bundle: NormalizedBundle,
  agentId: string,
): AgentModelDetails | undefined => {
  const route = bundle.agentRoutes[agentId]
  if (!route) {
    return undefined
  }
  const history = route.history?.length ? uniqueStrings(route.history) : []
  const label = route.last?.trim() || history[history.length - 1]
  if (!label) {
    return undefined
  }
  return {
    label,
    source: 'routed',
    provider: inferProvider(label),
    history: history.length ? history : [label],
  }
}

const formatSessionModelLabel = (
  session?: AgentSessionInfo,
): string | undefined => {
  if (!session) {
    return undefined
  }
  const provider = session.provider?.trim()
  const model = session.model?.trim()
  if (!model && !provider) {
    return undefined
  }
  if (!model) {
    return provider
  }
  if (
    provider &&
    !model.toLowerCase().startsWith(`${provider.toLowerCase()}/`)
  ) {
    return `${provider}/${model}`
  }
  return model
}

const inferProvider = (label?: string): string | undefined => {
  if (!label) {
    return undefined
  }
  const trimmed = label.trim()
  const slashIndex = trimmed.indexOf('/')
  if (slashIndex <= 0) {
    return undefined
  }
  return trimmed.slice(0, slashIndex)
}

const isRecord = (value: unknown): value is Record<string, unknown> => {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

const collectStringList = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return []
  }
  return value
    .map((entry) => (typeof entry === 'string' ? entry.trim() : ''))
    .filter((entry): entry is string => entry.length > 0)
}

const uniqueStrings = (values: string[]): string[] => {
  const seen = new Set<string>()
  const ordered: string[] = []
  values.forEach((value) => {
    if (!seen.has(value)) {
      seen.add(value)
      ordered.push(value)
    }
  })
  return ordered
}

export const getAgentModelDetails = (
  bundle: NormalizedBundle,
  agentId: string,
): AgentModelDetails => {
  const routed = extractRoutedModel(bundle, agentId)
  if (routed) {
    return routed
  }

  const session = bundle.agentSessions[agentId]
  const sessionLabel = formatSessionModelLabel(session)
  if (sessionLabel) {
    return {
      label: sessionLabel,
      source: 'session',
      provider: session?.provider || inferProvider(sessionLabel),
      history: session?.model ? [session.model] : [sessionLabel],
    }
  }

  const bundleModel =
    typeof bundle.raw.llm.model === 'string' ? bundle.raw.llm.model.trim() : ''
  const label = bundleModel || 'Unknown model'
  return {
    label,
    source: 'default',
    provider: inferProvider(label),
    history: bundleModel ? [bundleModel] : [],
  }
}

export const getAgentModelLabel = (
  bundle: NormalizedBundle,
  agentId: string,
): string => getAgentModelDetails(bundle, agentId).label
