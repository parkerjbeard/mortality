import clsx from 'clsx'

interface ViewToggleProps {
  view: 'board' | 'timeline'
  onChange: (view: 'board' | 'timeline') => void
}

const tabs: Array<{ id: 'board' | 'timeline'; label: string; description: string }> = [
  { id: 'board', label: 'Board + Drawer', description: 'Grid of agents with live event rail' },
  { id: 'timeline', label: 'Timeline Lanes', description: 'Synchronized time-axis lanes' },
]

export const ViewToggle = ({ view, onChange }: ViewToggleProps) => {
  return (
    <div className="flex flex-wrap gap-4">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          className={clsx(
            'flex-1 rounded-2xl border px-4 py-3 text-left transition',
            view === tab.id
              ? 'border-accent/60 bg-accent/5 text-white'
              : 'border-white/5 bg-white/5 text-slate-400 hover:border-white/20 hover:text-slate-100',
          )}
          onClick={() => onChange(tab.id)}
          type="button"
        >
          <div className="text-sm font-semibold">{tab.label}</div>
          <div className="text-xs text-slate-400">{tab.description}</div>
        </button>
      ))}
    </div>
  )
}
