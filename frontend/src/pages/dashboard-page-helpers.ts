import type { CommandAck } from '../types/api'

export const DEFAULT_INCIDENT_OPERATOR = 'emp_ops_1'

export function assertAcceptedCommand(ack: CommandAck, fallbackMessage: string) {
  if (ack.status === 'ACCEPTED' || ack.status === 'DUPLICATE') {
    return
  }
  throw new Error(ack.reason ?? fallbackMessage)
}

export function runtimeModeLabel(value: string | null | undefined) {
  switch (value) {
    case 'OPENAI_COMPAT_LIVE':
      return 'OpenAI Compat'
    case 'OPENAI_COMPAT_INCOMPLETE':
      return 'OpenAI Compat incomplete'
    case 'OPENAI_COMPAT_PAUSED':
      return 'OpenAI Compat paused'
    case 'LOCAL_DETERMINISTIC':
    default:
      return 'Local deterministic'
  }
}
