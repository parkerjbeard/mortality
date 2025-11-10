import {
  EVENT_CATEGORY_LABELS,
  EVENT_CATEGORY_ORDER,
  EventCategory,
  EventFilterState,
} from '@/lib/filters'

interface EventFiltersProps {
  filters: EventFilterState
  onToggle: (category: EventCategory) => void
}

export const EventFilters = ({ filters, onToggle }: EventFiltersProps) => {
  return (
    <div className="rounded-3xl border border-white/5 bg-panel/60 p-4 text-sm text-slate-300">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
            Event filters
          </p>
          <p className="text-[13px] text-slate-400">
            Toggle feed categories to focus on the signals you need.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {EVENT_CATEGORY_ORDER.map((category) => {
            const active = filters[category]
            return (
              <button
                key={category}
                type="button"
                onClick={() => onToggle(category)}
                aria-pressed={active}
                className={`rounded-full px-3 py-1 text-xs font-semibold tracking-wide transition ${
                  active
                    ? 'bg-white/20 text-white shadow-lg shadow-white/10'
                    : 'bg-white/5 text-slate-500 hover:bg-white/10 hover:text-slate-200'
                }`}
              >
                {EVENT_CATEGORY_LABELS[category]}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
