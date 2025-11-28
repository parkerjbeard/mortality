import { LiveMetrics } from '@/hooks/useLiveConnection'

interface LiveMetricsBarProps {
  metrics: LiveMetrics
  agentCount: number
}

export const LiveMetricsBar = ({ metrics, agentCount }: LiveMetricsBarProps) => {
  const elapsed = formatElapsed(metrics.elapsedMs)
  const aliveCount = agentCount - metrics.totalDeaths

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-white/5 bg-panel/40 px-4 py-3">
      <MetricPill
        label="Elapsed"
        value={elapsed}
        icon="clock"
      />
      <MetricPill
        label="Agents"
        value={`${aliveCount}/${agentCount}`}
        icon="users"
        variant={aliveCount === 0 ? 'danger' : 'default'}
      />
      <MetricPill
        label="Messages"
        value={metrics.totalMessages.toString()}
        icon="message"
      />
      <MetricPill
        label="Diary Entries"
        value={metrics.totalDiaryEntries.toString()}
        icon="diary"
        variant="success"
      />
      <MetricPill
        label="Broadcasts"
        value={metrics.totalBroadcasts.toString()}
        icon="broadcast"
      />
      <MetricPill
        label="Tool Calls"
        value={metrics.totalToolCalls.toString()}
        icon="tool"
      />
      {metrics.totalDeaths > 0 && (
        <MetricPill
          label="Deaths"
          value={metrics.totalDeaths.toString()}
          icon="death"
          variant="danger"
        />
      )}
    </div>
  )
}

interface MetricPillProps {
  label: string
  value: string
  icon: 'clock' | 'users' | 'message' | 'diary' | 'broadcast' | 'tool' | 'death'
  variant?: 'default' | 'success' | 'danger'
}

const MetricPill = ({ label, value, icon, variant = 'default' }: MetricPillProps) => {
  const variantClasses = {
    default: 'bg-white/5 text-slate-300',
    success: 'bg-emerald-500/10 text-emerald-300',
    danger: 'bg-rose-500/10 text-rose-300',
  }

  return (
    <div
      className={`flex items-center gap-2 rounded-xl px-3 py-1.5 ${variantClasses[variant]}`}
    >
      <MetricIcon type={icon} />
      <div className="flex items-baseline gap-1.5">
        <span className="font-mono text-sm font-semibold">{value}</span>
        <span className="text-[10px] uppercase tracking-wide text-slate-500">
          {label}
        </span>
      </div>
    </div>
  )
}

const MetricIcon = ({ type }: { type: MetricPillProps['icon'] }) => {
  const iconClass = 'h-3.5 w-3.5 text-slate-400'

  switch (type) {
    case 'clock':
      return (
        <svg className={iconClass} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      )
    case 'users':
      return (
        <svg className={iconClass} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197m13.5-9a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0z" />
        </svg>
      )
    case 'message':
      return (
        <svg className={iconClass} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      )
    case 'diary':
      return (
        <svg className={iconClass} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
        </svg>
      )
    case 'broadcast':
      return (
        <svg className={iconClass} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0" />
        </svg>
      )
    case 'tool':
      return (
        <svg className={iconClass} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      )
    case 'death':
      return (
        <svg className={iconClass} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
        </svg>
      )
  }
}

const formatElapsed = (ms: number): string => {
  if (!ms || ms < 0) return '0:00'

  const totalSeconds = Math.floor(ms / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
  }
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}
