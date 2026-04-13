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
      return 'OpenAI Compat (incomplete)'
    case 'OPENAI_COMPAT_PAUSED':
      return 'OpenAI Compat (paused)'
    case 'PROVIDER_REQUIRED_UNAVAILABLE':
      return 'Provider required'
    case 'CLAUDE_CODE_CLI_LIVE':
      return 'Claude Code CLI'
    case 'CLAUDE_CODE_CLI_INCOMPLETE':
      return 'Claude Code CLI (incomplete)'
    case 'CLAUDE_CODE_CLI_PAUSED':
      return 'Claude Code CLI (paused)'
    default:
      return 'Provider required'
  }
}

export function runtimeReasonLabel(value: string | null | undefined) {
  if (!value) {
    return 'No live provider is configured for runtime execution.'
  }
  return value
}
