import { postJson } from './client'
import type {
  BoardApproveRequest,
  BoardRejectRequest,
  CommandAck,
  EmployeeFreezeRequest,
  EmployeeHireRequest,
  EmployeeReplaceRequest,
  EmployeeRestoreRequest,
  IncidentResolveRequest,
  ModifyConstraintsRequest,
  ProjectInitRequest,
  RuntimeProviderUpsertRequest,
} from '../types/api'

export function projectInit(payload: ProjectInitRequest): Promise<CommandAck> {
  return postJson<CommandAck>('/api/v1/commands/project-init', payload)
}

export function runtimeProviderUpsert(payload: RuntimeProviderUpsertRequest): Promise<CommandAck> {
  return postJson<CommandAck>('/api/v1/commands/runtime-provider-upsert', payload)
}

export function boardApprove(payload: BoardApproveRequest): Promise<CommandAck> {
  return postJson<CommandAck>('/api/v1/commands/board-approve', payload)
}

export function boardReject(payload: BoardRejectRequest): Promise<CommandAck> {
  return postJson<CommandAck>('/api/v1/commands/board-reject', payload)
}

export function modifyConstraints(payload: ModifyConstraintsRequest): Promise<CommandAck> {
  return postJson<CommandAck>('/api/v1/commands/modify-constraints', payload)
}

export function incidentResolve(payload: IncidentResolveRequest): Promise<CommandAck> {
  return postJson<CommandAck>('/api/v1/commands/incident-resolve', payload)
}

export function employeeFreeze(payload: EmployeeFreezeRequest): Promise<CommandAck> {
  return postJson<CommandAck>('/api/v1/commands/employee-freeze', payload)
}

export function employeeRestore(payload: EmployeeRestoreRequest): Promise<CommandAck> {
  return postJson<CommandAck>('/api/v1/commands/employee-restore', payload)
}

export function employeeHireRequest(payload: EmployeeHireRequest): Promise<CommandAck> {
  return postJson<CommandAck>('/api/v1/commands/employee-hire-request', payload)
}

export function employeeReplaceRequest(payload: EmployeeReplaceRequest): Promise<CommandAck> {
  return postJson<CommandAck>('/api/v1/commands/employee-replace-request', payload)
}
