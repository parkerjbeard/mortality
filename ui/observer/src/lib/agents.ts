import { AgentProfile } from './bundle'

export const getAgentDisplayName = (
  profile: AgentProfile | undefined,
  fallbackId: string,
): string => {
  const name = profile?.display_name?.trim()
  return name && name.length > 0 ? name : fallbackId
}

export const getAgentInitials = (
  profile: AgentProfile | undefined,
  fallbackId: string,
): string => {
  const display = profile?.display_name?.trim()
  if (display) {
    const initials = display
      .split(' ')
      .map((part) => part[0])
      .join('')
      .slice(0, 2)
      .toUpperCase()
    if (initials) {
      return initials
    }
  }
  return fallbackId.slice(0, 2).toUpperCase()
}
