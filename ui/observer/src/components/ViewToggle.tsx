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
    <div className="inline-flex flex-wrap gap-2 rounded-full border border-white/10 bg-panel/30 p-1 text-xs">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          className={clsx(
            'rounded-full px-4 py-2 text-left transition',
            view === tab.id ? 'bg-white/10 text-white' : 'text-slate-400 hover:text-slate-100',
          )}
          onClick={() => onChange(tab.id)}
          type="button"
        >
          <div className="font-semibold">{tab.label}</div>
          <div className="text-[11px] text-slate-500">{tab.description}</div>
        </button>
      ))}
    </div>
  )
}
