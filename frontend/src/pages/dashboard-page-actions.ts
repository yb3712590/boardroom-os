import {
  boardApprove,
  boardReject,
  employeeFreeze,
  employeeHireRequest,
  employeeReplaceRequest,
  employeeRestore,
  incidentResolve,
  modifyConstraints,
  projectInit,
  runtimeProviderUpsert,
} from '../api/commands'
import type { IncidentDetailData } from '../types/api'
import type { StaffingHireTemplate } from '../types/domain'
import { newPrefixedId } from '../utils/ids'
import { assertAcceptedCommand, DEFAULT_INCIDENT_OPERATOR } from './dashboard-page-helpers'

type DashboardPageActionsArgs = {
  activeWorkflowId: string | null
  reviewPackId: string | undefined
  meetingId: string | undefined
  navigate: (path: string) => void
  loadSnapshot: () => Promise<void>
  reviewPack:
    | {
        meta: {
          review_pack_id: string
          review_pack_version: number
          approval_id: string
        }
        decision_form: {
          command_target_version: number
        }
      }
    | null
    | undefined
  incidentDetail: IncidentDetailData | null
  setProjectInitPending: (value: boolean) => void
  setSnapshotError: (value: string | null) => void
  setRuntimeProviderError: (value: string | null) => void
  setProviderSettingsOpen: (value: boolean) => void
  setRuntimeProviderSubmitting: (value: boolean) => void
  setSubmittingIncidentAction: (value: boolean) => void
  setIncidentError: (value: string | null) => void
  setSubmittingStaffingAction: (value: string | null) => void
  setSubmittingAction: (value: string | null) => void
  setReviewError: (value: string | null) => void
}

export function useDashboardPageActions({
  activeWorkflowId,
  reviewPackId,
  meetingId,
  navigate,
  loadSnapshot,
  reviewPack,
  incidentDetail,
  setProjectInitPending,
  setSnapshotError,
  setRuntimeProviderError,
  setProviderSettingsOpen,
  setRuntimeProviderSubmitting,
  setSubmittingIncidentAction,
  setIncidentError,
  setSubmittingStaffingAction,
  setSubmittingAction,
  setReviewError,
}: DashboardPageActionsArgs) {
  const handleOpenReview = (packId: string) => {
    navigate(`/review/${packId}`)
  }

  const handleOpenIncident = (nextIncidentId: string) => {
    navigate(`/incident/${nextIncidentId}`)
  }

  const handleOpenMeeting = (nextMeetingId: string) => {
    navigate(`/meeting/${nextMeetingId}`)
  }

  const handleProjectInit = async (payload: {
    northStarGoal: string
    hardConstraints: string[]
    budgetCap: number
    forceRequirementElicitation: boolean
  }) => {
    setProjectInitPending(true)
    setSnapshotError(null)
    try {
      await projectInit({
        north_star_goal: payload.northStarGoal,
        hard_constraints: payload.hardConstraints,
        budget_cap: payload.budgetCap,
        deadline_at: null,
        force_requirement_elicitation: payload.forceRequirementElicitation,
      })
      await loadSnapshot()
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : 'Failed to launch the local workflow.')
    } finally {
      setProjectInitPending(false)
    }
  }

  const handleRuntimeProviderSave = async (input: {
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
  }) => {
    setRuntimeProviderSubmitting(true)
    setRuntimeProviderError(null)
    try {
      await runtimeProviderUpsert({
        default_provider_id: input.defaultProviderId,
        providers: input.providers,
        role_bindings: input.roleBindings,
        idempotency_key: newPrefixedId('runtime-provider-upsert'),
      })
      await loadSnapshot()
      setProviderSettingsOpen(false)
    } catch (error) {
      setRuntimeProviderError(error instanceof Error ? error.message : 'Failed to save runtime provider settings.')
    } finally {
      setRuntimeProviderSubmitting(false)
    }
  }

  const handleIncidentResolve = async (input: {
    resolutionSummary: string
    followupAction: string
  }) => {
    if (!incidentDetail) {
      return
    }
    setSubmittingIncidentAction(true)
    try {
      await incidentResolve({
        incident_id: incidentDetail.incident.incident_id,
        resolved_by: DEFAULT_INCIDENT_OPERATOR,
        resolution_summary: input.resolutionSummary,
        followup_action: input.followupAction,
        idempotency_key: newPrefixedId('incident-resolve'),
      })
      await loadSnapshot()
      navigate('/')
    } catch (error) {
      setIncidentError(error instanceof Error ? error.message : 'Incident recovery failed.')
    } finally {
      setSubmittingIncidentAction(false)
    }
  }

  const handleEmployeeFreeze = async (employeeId: string) => {
    if (!activeWorkflowId) {
      return
    }
    const actionKey = `freeze:${employeeId}`
    setSubmittingStaffingAction(actionKey)
    setSnapshotError(null)
    try {
      const ack = await employeeFreeze({
        workflow_id: activeWorkflowId,
        employee_id: employeeId,
        frozen_by: DEFAULT_INCIDENT_OPERATOR,
        reason: 'Pause this worker from taking new tickets.',
        idempotency_key: newPrefixedId('employee-freeze'),
      })
      assertAcceptedCommand(ack, 'Employee freeze failed.')
      await loadSnapshot()
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : 'Employee freeze failed.')
    } finally {
      setSubmittingStaffingAction(null)
    }
  }

  const handleEmployeeRestore = async (employeeId: string) => {
    if (!activeWorkflowId) {
      return
    }
    const actionKey = `restore:${employeeId}`
    setSubmittingStaffingAction(actionKey)
    setSnapshotError(null)
    try {
      const ack = await employeeRestore({
        workflow_id: activeWorkflowId,
        employee_id: employeeId,
        restored_by: DEFAULT_INCIDENT_OPERATOR,
        reason: 'Return this worker to active duty.',
        idempotency_key: newPrefixedId('employee-restore'),
      })
      assertAcceptedCommand(ack, 'Employee restore failed.')
      await loadSnapshot()
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : 'Employee restore failed.')
    } finally {
      setSubmittingStaffingAction(null)
    }
  }

  const handleEmployeeHireRequest = async (template: StaffingHireTemplate, employeeId: string) => {
    if (!activeWorkflowId) {
      return
    }
    const actionKey = `hire:${template.template_id}`
    setSubmittingStaffingAction(actionKey)
    setSnapshotError(null)
    try {
      const ack = await employeeHireRequest({
        workflow_id: activeWorkflowId,
        employee_id: employeeId,
        role_type: template.role_type,
        role_profile_refs: template.role_profile_refs,
        skill_profile: template.skill_profile,
        personality_profile: template.personality_profile,
        aesthetic_profile: template.aesthetic_profile,
        provider_id: template.provider_id,
        request_summary: template.request_summary,
        idempotency_key: newPrefixedId('employee-hire-request'),
      })
      assertAcceptedCommand(ack, 'Employee hire request failed.')
      await loadSnapshot()
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : 'Employee hire request failed.')
    } finally {
      setSubmittingStaffingAction(null)
    }
  }

  const handleEmployeeReplaceRequest = async (
    employeeId: string,
    template: StaffingHireTemplate,
    replacementEmployeeId: string,
  ) => {
    if (!activeWorkflowId) {
      return
    }
    const actionKey = `replace:${employeeId}`
    setSubmittingStaffingAction(actionKey)
    setSnapshotError(null)
    try {
      const ack = await employeeReplaceRequest({
        workflow_id: activeWorkflowId,
        replaced_employee_id: employeeId,
        replacement_employee_id: replacementEmployeeId,
        replacement_role_type: template.role_type,
        replacement_role_profile_refs: template.role_profile_refs,
        replacement_skill_profile: template.skill_profile,
        replacement_personality_profile: template.personality_profile,
        replacement_aesthetic_profile: template.aesthetic_profile,
        replacement_provider_id: template.provider_id,
        request_summary: `Replace ${employeeId} with a supported ${template.label.toLowerCase()} to keep the local delivery loop moving.`,
        idempotency_key: newPrefixedId('employee-replace-request'),
      })
      assertAcceptedCommand(ack, 'Employee replacement request failed.')
      await loadSnapshot()
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : 'Employee replacement request failed.')
    } finally {
      setSubmittingStaffingAction(null)
    }
  }

  const handleApprove = async (input: {
    selectedOptionId: string
    boardComment: string
    elicitationAnswers?: Array<{
      question_id: string
      selected_option_ids: string[]
      text: string
    }>
  }) => {
    if (!reviewPack) {
      return
    }
    setSubmittingAction('APPROVE')
    try {
      await boardApprove({
        review_pack_id: reviewPack.meta.review_pack_id,
        review_pack_version: reviewPack.meta.review_pack_version,
        command_target_version: reviewPack.decision_form.command_target_version,
        approval_id: reviewPack.meta.approval_id,
        selected_option_id: input.selectedOptionId,
        board_comment: input.boardComment,
        elicitation_answers: input.elicitationAnswers,
        idempotency_key: newPrefixedId('board-approve'),
      })
      await loadSnapshot()
      navigate('/')
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : 'Board approve failed.')
    } finally {
      setSubmittingAction(null)
    }
  }

  const handleReject = async (input: { boardComment: string; rejectionReasons: string[] }) => {
    if (!reviewPack) {
      return
    }
    setSubmittingAction('REJECT')
    try {
      await boardReject({
        review_pack_id: reviewPack.meta.review_pack_id,
        review_pack_version: reviewPack.meta.review_pack_version,
        command_target_version: reviewPack.decision_form.command_target_version,
        approval_id: reviewPack.meta.approval_id,
        board_comment: input.boardComment,
        rejection_reasons: input.rejectionReasons,
        idempotency_key: newPrefixedId('board-reject'),
      })
      await loadSnapshot()
      navigate('/')
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : 'Board reject failed.')
    } finally {
      setSubmittingAction(null)
    }
  }

  const handleModifyConstraints = async (input: {
    boardComment: string
    addRules: string[]
    removeRules: string[]
    replaceRules: string[]
    elicitationAnswers?: Array<{
      question_id: string
      selected_option_ids: string[]
      text: string
    }>
  }) => {
    if (!reviewPack) {
      return
    }
    setSubmittingAction('MODIFY_CONSTRAINTS')
    try {
      await modifyConstraints({
        review_pack_id: reviewPack.meta.review_pack_id,
        review_pack_version: reviewPack.meta.review_pack_version,
        command_target_version: reviewPack.decision_form.command_target_version,
        approval_id: reviewPack.meta.approval_id,
        constraint_patch: {
          add_rules: input.addRules,
          remove_rules: input.removeRules,
          replace_rules: input.replaceRules,
        },
        board_comment: input.boardComment,
        elicitation_answers: input.elicitationAnswers,
        idempotency_key: newPrefixedId('modify-constraints'),
      })
      await loadSnapshot()
      navigate('/')
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : 'Constraint update failed.')
    } finally {
      setSubmittingAction(null)
    }
  }

  return {
    handleOpenReview,
    handleOpenMeeting,
    handleOpenIncident,
    handleProjectInit,
    handleRuntimeProviderSave,
    handleIncidentResolve,
    handleEmployeeFreeze,
    handleEmployeeRestore,
    handleEmployeeHireRequest,
    handleEmployeeReplaceRequest,
    handleApprove,
    handleReject,
    handleModifyConstraints,
    closeReviewRoom: () => navigate('/'),
    closeMeeting: () => {
      if (!meetingId) {
        navigate('/')
        return
      }
      navigate('/')
    },
    closeIncident: () => navigate('/'),
    openInspectorForReview: async (
      loadDeveloperInspector: (packId: string) => Promise<void>,
    ) => {
      if (!reviewPackId) {
        return
      }
      await loadDeveloperInspector(reviewPackId)
    },
  }
}
