export type EventCategory = 'broadcast' | 'diary' | 'tool' | 'system'

export const EVENT_CATEGORY_LABELS: Record<EventCategory, string> = {
  broadcast: 'Broadcast',
  diary: 'Diary',
  tool: 'Tool',
  system: 'System',
}

export const EVENT_CATEGORY_ORDER: EventCategory[] = [
  'broadcast',
  'diary',
  'tool',
  'system',
]

export type EventFilterState = Record<EventCategory, boolean>

export const createDefaultFilterState = (): EventFilterState => ({
  broadcast: true,
  diary: true,
  tool: true,
  system: true,
})
