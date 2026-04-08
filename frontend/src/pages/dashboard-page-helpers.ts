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
      return 'OpenAI 兼容'
    case 'OPENAI_COMPAT_INCOMPLETE':
      return 'OpenAI 兼容（配置不完整）'
    case 'OPENAI_COMPAT_PAUSED':
      return 'OpenAI 兼容（已暂停）'
    case 'CLAUDE_CODE_CLI_LIVE':
      return 'Claude Code CLI'
    case 'CLAUDE_CODE_CLI_INCOMPLETE':
      return 'Claude Code CLI（配置不完整）'
    case 'CLAUDE_CODE_CLI_PAUSED':
      return 'Claude Code CLI（已暂停）'
    case 'LOCAL_DETERMINISTIC':
    default:
      return '本地确定性执行'
  }
}

export function runtimeReasonLabel(value: string | null | undefined) {
  if (!value) {
    return '当前按已保存的本地执行设置运行。'
  }
  if (value === 'Runtime is using the local deterministic path.') {
    return '当前使用本地确定性执行路径。'
  }
  if (value === 'Runtime is using the currently saved local execution settings.') {
    return '当前按已保存的本地执行设置运行。'
  }
  return value
}
