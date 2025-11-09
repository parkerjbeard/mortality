import clsx from 'clsx'

interface CountdownRingProps {
  value: number | null
  max: number | null
  label: string
  caption?: string
}

export const CountdownRing = ({ value, max, label, caption = 'time left' }: CountdownRingProps) => {
  const radius = 30
  const circumference = 2 * Math.PI * radius
  const progress = max && value !== null ? Math.max(0, Math.min(1, value / max)) : 0
  const offset = circumference * (1 - progress)
  const tone = progress > 0.6 ? 'stroke-accent' : progress > 0.3 ? 'stroke-warning' : 'stroke-danger'

  return (
    <div className="relative h-20 w-20">
      <svg className="h-20 w-20 -rotate-90 transform text-slate-700" viewBox="0 0 80 80">
        <circle cx="40" cy="40" r={radius} className="stroke-white/10" strokeWidth="8" fill="transparent" />
        <circle
          cx="40"
          cy="40"
          r={radius}
          className={clsx('fill-transparent transition-all duration-200', tone)}
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-lg font-semibold text-white">{label}</span>
        <span className="text-[11px] uppercase tracking-wide text-slate-400">{caption}</span>
      </div>
    </div>
  )
}
