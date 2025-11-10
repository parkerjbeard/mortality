import clsx from 'clsx'

interface AgentModelBadgeProps {
  label: string
  className?: string
}

export const AgentModelBadge = ({ label, className }: AgentModelBadgeProps) => {
  return (
    <span
      className={clsx(
        'rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] font-medium text-slate-300',
        className,
      )}
    >
      {label}
    </span>
  )
}
