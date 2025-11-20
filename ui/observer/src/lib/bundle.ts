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

export interface NormalizedBundle {
  raw: RawBundle
  events: NormalizedEvent[]
  diaries: Record<string, NormalizedDiaryEntry[]>
  agents: Record<string, AgentProfile>
  agentOrder: string[]
  timeline: {
    startMs: number
    endMs: number
    durationMs: number
  }
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

  return {
    raw,
    events,
    diaries,
    agents: raw.agents,
    agentOrder,
    timeline: { startMs, endMs, durationMs },
  }
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
