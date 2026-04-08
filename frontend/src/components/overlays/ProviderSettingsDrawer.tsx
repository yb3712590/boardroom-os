import { useEffect, useState } from 'react'

import type { RuntimeProviderData, RuntimeProviderRoleBinding } from '../../types/api'
import { Drawer } from '../shared/Drawer'

const OPENAI_PROVIDER_ID = 'prov_openai_compat'
const CLAUDE_PROVIDER_ID = 'prov_claude_code'

const CURRENT_ROLE_TARGETS = [
  { target_ref: 'ceo_shadow', target_label: 'CEO 影子角色' },
  { target_ref: 'role_profile:ui_designer_primary', target_label: '范围共识' },
  { target_ref: 'role_profile:frontend_engineer_primary', target_label: '前端工程师' },
  { target_ref: 'role_profile:checker_primary', target_label: '检查员' },
  { target_ref: 'role_profile:backend_engineer_primary', target_label: '后端工程师 / 服务交付' },
  { target_ref: 'role_profile:database_engineer_primary', target_label: '数据库工程师 / 数据可靠性' },
  { target_ref: 'role_profile:platform_sre_primary', target_label: '平台 / SRE' },
  { target_ref: 'role_profile:architect_primary', target_label: '架构师 / 设计评审' },
  { target_ref: 'role_profile:cto_primary', target_label: 'CTO / 架构治理' },
]

const PROVIDER_CAPABILITY_OPTIONS = [
  { value: 'structured_output', label: '结构化输出' },
  { value: 'planning', label: '规划' },
  { value: 'implementation', label: '实施' },
  { value: 'review', label: '评审' },
] as const

function formatBoundaryPathRef(ref: string) {
  return ref.replaceAll('_', ' ')
}

type EditableRoleBinding = {
  target_ref: string
  target_label: string
  provider_id: string
  model: string
}

type ProviderSettingsDrawerProps = {
  isOpen: boolean
  providerData: RuntimeProviderData | null
  loading: boolean
  error: string | null
  submitting: boolean
  onClose: () => void
  onSave: (input: {
    defaultProviderId: string | null
    providers: Array<{
      provider_id: string
      adapter_kind: string
      label: string
      enabled: boolean
      base_url: string | null
      api_key: string | null
      model: string | null
      timeout_sec: number
      reasoning_effort: string | null
      command_path: string | null
      capability_tags: string[]
      cost_tier: string
      participation_policy: string
      fallback_provider_ids: string[]
    }>
    roleBindings: Array<{
      target_ref: string
      provider_id: string
      model: string | null
    }>
  }) => Promise<void>
}

function providerBindingMap(bindings: RuntimeProviderRoleBinding[] | undefined) {
  return new Map((bindings ?? []).map((binding) => [binding.target_ref, binding]))
}

function buildEditableBindings(providerData: RuntimeProviderData | null): EditableRoleBinding[] {
  const bindingByRef = providerBindingMap(providerData?.role_bindings)
  return CURRENT_ROLE_TARGETS.map((target) => {
    const binding = bindingByRef.get(target.target_ref)
    return {
      target_ref: target.target_ref,
      target_label: target.target_label,
      provider_id: binding?.provider_id ?? '',
      model: binding?.model ?? '',
    }
  })
}

export function ProviderSettingsDrawer({
  isOpen,
  providerData,
  loading,
  error,
  submitting,
  onClose,
  onSave,
}: ProviderSettingsDrawerProps) {
  const openaiProvider = providerData?.providers.find((provider) => provider.provider_id === OPENAI_PROVIDER_ID)
  const claudeProvider = providerData?.providers.find((provider) => provider.provider_id === CLAUDE_PROVIDER_ID)

  const [mode, setMode] = useState(providerData?.mode ?? 'DETERMINISTIC')
  const [openaiBaseUrl, setOpenaiBaseUrl] = useState(openaiProvider?.base_url ?? '')
  const [openaiApiKey, setOpenaiApiKey] = useState('')
  const [openaiModel, setOpenaiModel] = useState(openaiProvider?.model ?? '')
  const [openaiTimeoutSec, setOpenaiTimeoutSec] = useState(String(openaiProvider?.timeout_sec ?? 30))
  const [openaiReasoningEffort, setOpenaiReasoningEffort] = useState(openaiProvider?.reasoning_effort ?? '')
  const [openaiCapabilityTags, setOpenaiCapabilityTags] = useState<string[]>(openaiProvider?.capability_tags ?? [])
  const [openaiCostTier, setOpenaiCostTier] = useState(openaiProvider?.cost_tier ?? 'standard')
  const [openaiParticipationPolicy, setOpenaiParticipationPolicy] = useState(
    openaiProvider?.participation_policy ?? 'always_allowed',
  )
  const [openaiFallbackProviderId, setOpenaiFallbackProviderId] = useState(
    openaiProvider?.fallback_provider_ids?.[0] ?? '',
  )
  const [claudeCommandPath, setClaudeCommandPath] = useState(claudeProvider?.command_path ?? '')
  const [claudeModel, setClaudeModel] = useState(claudeProvider?.model ?? '')
  const [claudeTimeoutSec, setClaudeTimeoutSec] = useState(String(claudeProvider?.timeout_sec ?? 30))
  const [claudeCapabilityTags, setClaudeCapabilityTags] = useState<string[]>(claudeProvider?.capability_tags ?? [])
  const [claudeCostTier, setClaudeCostTier] = useState(claudeProvider?.cost_tier ?? 'premium')
  const [claudeParticipationPolicy, setClaudeParticipationPolicy] = useState(
    claudeProvider?.participation_policy ?? 'low_frequency_only',
  )
  const [claudeFallbackProviderId, setClaudeFallbackProviderId] = useState(
    claudeProvider?.fallback_provider_ids?.[0] ?? '',
  )
  const [roleBindings, setRoleBindings] = useState<EditableRoleBinding[]>(buildEditableBindings(providerData))

  useEffect(() => {
    if (!isOpen) {
      return
    }
    const nextOpenaiProvider = providerData?.providers.find((provider) => provider.provider_id === OPENAI_PROVIDER_ID)
    const nextClaudeProvider = providerData?.providers.find((provider) => provider.provider_id === CLAUDE_PROVIDER_ID)
    setMode(providerData?.mode ?? 'DETERMINISTIC')
    setOpenaiBaseUrl(nextOpenaiProvider?.base_url ?? '')
    setOpenaiApiKey('')
    setOpenaiModel(nextOpenaiProvider?.model ?? '')
    setOpenaiTimeoutSec(String(nextOpenaiProvider?.timeout_sec ?? 30))
    setOpenaiReasoningEffort(nextOpenaiProvider?.reasoning_effort ?? '')
    setOpenaiCapabilityTags(nextOpenaiProvider?.capability_tags ?? [])
    setOpenaiCostTier(nextOpenaiProvider?.cost_tier ?? 'standard')
    setOpenaiParticipationPolicy(nextOpenaiProvider?.participation_policy ?? 'always_allowed')
    setOpenaiFallbackProviderId(nextOpenaiProvider?.fallback_provider_ids?.[0] ?? '')
    setClaudeCommandPath(nextClaudeProvider?.command_path ?? '')
    setClaudeModel(nextClaudeProvider?.model ?? '')
    setClaudeTimeoutSec(String(nextClaudeProvider?.timeout_sec ?? 30))
    setClaudeCapabilityTags(nextClaudeProvider?.capability_tags ?? [])
    setClaudeCostTier(nextClaudeProvider?.cost_tier ?? 'premium')
    setClaudeParticipationPolicy(nextClaudeProvider?.participation_policy ?? 'low_frequency_only')
    setClaudeFallbackProviderId(nextClaudeProvider?.fallback_provider_ids?.[0] ?? '')
    setRoleBindings(buildEditableBindings(providerData))
  }, [isOpen, providerData])

  const updateBinding = (targetRef: string, patch: Partial<EditableRoleBinding>) => {
    setRoleBindings((current) =>
      current.map((binding) => (binding.target_ref === targetRef ? { ...binding, ...patch } : binding)),
    )
  }

  const toggleCapability = (
    currentTags: string[],
    nextTag: string,
    setTags: (value: string[] | ((current: string[]) => string[])) => void,
  ) => {
    if (currentTags.includes(nextTag)) {
      setTags(currentTags.filter((tag) => tag !== nextTag))
      return
    }
    const ordered = PROVIDER_CAPABILITY_OPTIONS.map((option) => option.value).filter(
      (option) => option === nextTag || currentTags.includes(option),
    )
    setTags(ordered)
  }

  const handleSave = () => {
    const selectedProviderIds = new Set(
      roleBindings.map((binding) => binding.provider_id).filter((providerId) => providerId.length > 0),
    )
    const defaultProviderId =
      mode === 'OPENAI_COMPAT' ? OPENAI_PROVIDER_ID : mode === 'CLAUDE_CODE_CLI' ? CLAUDE_PROVIDER_ID : null
    if (defaultProviderId) {
      selectedProviderIds.add(defaultProviderId)
    }

    void onSave({
      defaultProviderId,
      providers: [
        {
          provider_id: OPENAI_PROVIDER_ID,
          adapter_kind: 'openai_compat',
          label: 'OpenAI Compat',
          enabled:
            selectedProviderIds.has(OPENAI_PROVIDER_ID) ||
            Boolean(openaiBaseUrl.trim() || openaiModel.trim() || openaiApiKey.trim()),
          base_url: openaiBaseUrl.trim() || null,
          api_key: openaiApiKey.trim() || null,
          model: openaiModel.trim() || null,
          timeout_sec: Number.parseFloat(openaiTimeoutSec) || 30,
          reasoning_effort: openaiReasoningEffort || null,
          command_path: null,
          capability_tags: openaiCapabilityTags,
          cost_tier: openaiCostTier,
          participation_policy: openaiParticipationPolicy,
          fallback_provider_ids: openaiFallbackProviderId ? [openaiFallbackProviderId] : [],
        },
        {
          provider_id: CLAUDE_PROVIDER_ID,
          adapter_kind: 'claude_code_cli',
          label: 'Claude Code CLI',
          enabled:
            selectedProviderIds.has(CLAUDE_PROVIDER_ID) || Boolean(claudeCommandPath.trim() || claudeModel.trim()),
          base_url: null,
          api_key: null,
          model: claudeModel.trim() || null,
          timeout_sec: Number.parseFloat(claudeTimeoutSec) || 30,
          reasoning_effort: null,
          command_path: claudeCommandPath.trim() || null,
          capability_tags: claudeCapabilityTags,
          cost_tier: claudeCostTier,
          participation_policy: claudeParticipationPolicy,
          fallback_provider_ids: claudeFallbackProviderId ? [claudeFallbackProviderId] : [],
        },
      ],
      roleBindings: roleBindings
        .filter((binding) => binding.provider_id.length > 0)
        .map((binding) => ({
          target_ref: binding.target_ref,
          provider_id: binding.provider_id,
          model: binding.model.trim() || null,
        })),
    })
  }

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="运行时供应商" subtitle="运行时">
      <p className="muted-copy">
        在不离开董事会界面的前提下，管理本地供应商注册表、选择默认运行路径，并为当前在线角色绑定
        OpenAI 兼容或 Claude Code CLI。
      </p>

      {loading ? (
        <div className="review-room-state">正在加载运行时供应商...</div>
      ) : error ? (
        <div className="review-room-state review-room-error">{error}</div>
      ) : (
        <div className="review-room-content">
          <section className="review-room-overview">
            <div>
              <span className="eyebrow">生效模式</span>
              <p>{providerData?.effective_mode ?? '未知'}</p>
            </div>
            <div>
              <span className="eyebrow">健康状态</span>
              <p>{providerData?.provider_health_summary ?? '未知'}</p>
            </div>
            <div>
              <span className="eyebrow">默认供应商</span>
              <p>{providerData?.default_provider_id ?? '仅本地确定性模式'}</p>
            </div>
            <div>
              <span className="eyebrow">执行人数</span>
              <p>{providerData?.configured_worker_count ?? 0}</p>
            </div>
          </section>
          <p className="muted-copy">{providerData?.effective_reason ?? '运行时供应商状态暂不可用。'}</p>

          <section className="review-room-action-panel provider-settings-panel">
            <label>
              <span className="field-label">供应商模式</span>
              <select
                aria-label="供应商模式"
                value={mode}
                onChange={(event) => setMode(event.target.value)}
                disabled={submitting}
              >
                <option value="DETERMINISTIC">本地确定性</option>
                <option value="OPENAI_COMPAT">OpenAI 兼容</option>
                <option value="CLAUDE_CODE_CLI">Claude Code CLI</option>
              </select>
            </label>

            <section className="review-room-overview">
              <div>
                <span className="eyebrow">OpenAI 密钥</span>
                <p>{openaiProvider?.api_key_masked ?? '未保存密钥'}</p>
              </div>
              <div>
                <span className="eyebrow">Claude 命令</span>
                <p>{claudeProvider?.command_path ?? '未配置'}</p>
              </div>
              <div>
                <span className="eyebrow">OpenAI 绑定人数</span>
                <p>{openaiProvider?.configured_worker_count ?? 0}</p>
              </div>
              <div>
                <span className="eyebrow">Claude 绑定人数</span>
                <p>{claudeProvider?.configured_worker_count ?? 0}</p>
              </div>
              <div>
                <span className="eyebrow">OpenAI 健康</span>
                <p>{openaiProvider?.health_status ?? '未知'}</p>
              </div>
              <div>
                <span className="eyebrow">Claude 健康</span>
                <p>{claudeProvider?.health_status ?? '未知'}</p>
              </div>
            </section>
            <p className="muted-copy">{openaiProvider?.health_reason ?? 'OpenAI 健康明细暂不可用。'}</p>
            <p className="muted-copy">{claudeProvider?.health_reason ?? 'Claude 健康明细暂不可用。'}</p>

            <label>
              <span className="field-label">OpenAI Base URL</span>
              <input
                aria-label="OpenAI Base URL"
                value={openaiBaseUrl}
                onChange={(event) => setOpenaiBaseUrl(event.target.value)}
              />
            </label>
            <label>
              <span className="field-label">OpenAI API Key</span>
              <input
                aria-label="OpenAI API Key"
                type="password"
                value={openaiApiKey}
                placeholder={openaiProvider?.api_key_masked ?? ''}
                onChange={(event) => setOpenaiApiKey(event.target.value)}
              />
            </label>
            <label>
              <span className="field-label">OpenAI 模型</span>
              <input
                aria-label="OpenAI 模型"
                value={openaiModel}
                onChange={(event) => setOpenaiModel(event.target.value)}
              />
            </label>
            <div className="provider-settings-grid">
              <label>
                <span className="field-label">OpenAI 超时（秒）</span>
                <input
                  aria-label="OpenAI 超时（秒）"
                  type="number"
                  min="1"
                  value={openaiTimeoutSec}
                  onChange={(event) => setOpenaiTimeoutSec(event.target.value)}
                />
              </label>
              <label>
                <span className="field-label">OpenAI 推理强度</span>
                <select
                  aria-label="OpenAI 推理强度"
                  value={openaiReasoningEffort}
                  onChange={(event) => setOpenaiReasoningEffort(event.target.value)}
                >
                  <option value="">默认</option>
                  <option value="low">低</option>
                  <option value="medium">中</option>
                  <option value="high">高</option>
                  <option value="xhigh">极高</option>
                </select>
              </label>
            </div>

            <div>
              <span className="field-label">OpenAI 能力标签</span>
              <div className="provider-settings-grid">
                {PROVIDER_CAPABILITY_OPTIONS.map((option) => (
                  <label key={`openai-capability-${option.value}`}>
                    <input
                      aria-label={`OpenAI 能力 ${option.value}`}
                      type="checkbox"
                      checked={openaiCapabilityTags.includes(option.value)}
                      onChange={() => toggleCapability(openaiCapabilityTags, option.value, setOpenaiCapabilityTags)}
                    />
                    <span>{option.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="provider-settings-grid">
              <label>
                <span className="field-label">OpenAI 成本等级</span>
                <select
                  aria-label="OpenAI 成本等级"
                  value={openaiCostTier}
                  onChange={(event) => setOpenaiCostTier(event.target.value)}
                >
                  <option value="standard">标准</option>
                  <option value="premium">高级</option>
                </select>
              </label>
              <label>
                <span className="field-label">OpenAI 参与策略</span>
                <select
                  aria-label="OpenAI 参与策略"
                  value={openaiParticipationPolicy}
                  onChange={(event) => setOpenaiParticipationPolicy(event.target.value)}
                >
                  <option value="always_allowed">始终允许</option>
                  <option value="low_frequency_only">仅低频参与</option>
                </select>
              </label>
            </div>

            <label>
              <span className="field-label">OpenAI 失败回退供应商</span>
              <select
                aria-label="OpenAI 回退供应商"
                value={openaiFallbackProviderId}
                onChange={(event) => setOpenaiFallbackProviderId(event.target.value)}
              >
                <option value="">不启用回退</option>
                <option value={CLAUDE_PROVIDER_ID}>Claude Code CLI</option>
              </select>
            </label>

            <label>
              <span className="field-label">Claude 命令路径</span>
              <input
                aria-label="Claude 命令路径"
                value={claudeCommandPath}
                onChange={(event) => setClaudeCommandPath(event.target.value)}
              />
            </label>
            <label>
              <span className="field-label">Claude 模型</span>
              <input
                aria-label="Claude 模型"
                value={claudeModel}
                onChange={(event) => setClaudeModel(event.target.value)}
              />
            </label>
            <label>
              <span className="field-label">Claude 超时（秒）</span>
              <input
                aria-label="Claude 超时（秒）"
                type="number"
                min="1"
                value={claudeTimeoutSec}
                onChange={(event) => setClaudeTimeoutSec(event.target.value)}
              />
            </label>

            <div>
              <span className="field-label">Claude 能力标签</span>
              <div className="provider-settings-grid">
                {PROVIDER_CAPABILITY_OPTIONS.map((option) => (
                  <label key={`claude-capability-${option.value}`}>
                    <input
                      aria-label={`Claude 能力 ${option.value}`}
                      type="checkbox"
                      checked={claudeCapabilityTags.includes(option.value)}
                      onChange={() => toggleCapability(claudeCapabilityTags, option.value, setClaudeCapabilityTags)}
                    />
                    <span>{option.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="provider-settings-grid">
              <label>
                <span className="field-label">Claude 成本等级</span>
                <select
                  aria-label="Claude 成本等级"
                  value={claudeCostTier}
                  onChange={(event) => setClaudeCostTier(event.target.value)}
                >
                  <option value="standard">标准</option>
                  <option value="premium">高级</option>
                </select>
              </label>
              <label>
                <span className="field-label">Claude 参与策略</span>
                <select
                  aria-label="Claude 参与策略"
                  value={claudeParticipationPolicy}
                  onChange={(event) => setClaudeParticipationPolicy(event.target.value)}
                >
                  <option value="always_allowed">始终允许</option>
                  <option value="low_frequency_only">仅低频参与</option>
                </select>
              </label>
            </div>

            <label>
              <span className="field-label">Claude 失败回退供应商</span>
              <select
                aria-label="Claude 回退供应商"
                value={claudeFallbackProviderId}
                onChange={(event) => setClaudeFallbackProviderId(event.target.value)}
              >
                <option value="">不启用回退</option>
                <option value={OPENAI_PROVIDER_ID}>OpenAI 兼容</option>
              </select>
            </label>

            <div>
              <span className="field-label">当前角色绑定</span>
              <div className="provider-settings-grid">
                {roleBindings.map((binding) => (
                  <label key={binding.target_ref}>
                    <span className="field-label">{binding.target_label}</span>
                    <select
                      aria-label={`${binding.target_label} 供应商`}
                      value={binding.provider_id}
                      onChange={(event) => updateBinding(binding.target_ref, { provider_id: event.target.value })}
                    >
                      <option value="">跟随默认</option>
                      <option value={OPENAI_PROVIDER_ID}>OpenAI 兼容</option>
                      <option value={CLAUDE_PROVIDER_ID}>Claude Code CLI</option>
                    </select>
                    <input
                      aria-label={`${binding.target_label} 模型覆写`}
                      value={binding.model}
                      placeholder="模型覆写（可选）"
                      onChange={(event) => updateBinding(binding.target_ref, { model: event.target.value })}
                    />
                  </label>
                ))}
              </div>
            </div>

            {providerData?.future_binding_slots?.length ? (
              <div>
                <span className="field-label">预留绑定位</span>
                <p className="muted-copy">
                  仅目录角色在后续主线路角色纳入之前保持只读。
                </p>
                <div className="provider-settings-grid">
                  {providerData.future_binding_slots.map((slot) => (
                    <label key={slot.target_ref}>
                      <span className="field-label">{slot.label}</span>
                      <input aria-label={`${slot.label} status`} value={`${slot.status}: ${slot.reason}`} disabled />
                      {slot.blocked_path_refs.length > 0 ? (
                        <span className="muted-copy">
                          {`受阻面：${slot.blocked_path_refs.map(formatBoundaryPathRef).join(', ')}`}
                        </span>
                      ) : null}
                    </label>
                  ))}
                </div>
              </div>
            ) : null}

            <button type="button" className="secondary-button" disabled={submitting} onClick={handleSave}>
              {submitting ? '保存中...' : '保存运行时设置'}
            </button>
          </section>
        </div>
      )}
    </Drawer>
  )
}
