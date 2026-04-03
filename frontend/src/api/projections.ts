import { getJson } from './client'
import type {
  DashboardData,
  DependencyInspectorData,
  DeveloperInspectorData,
  InboxData,
  IncidentDetailData,
  ProjectionEnvelope,
  ReviewRoomData,
  RuntimeProviderData,
  WorkforceData,
} from '../types/api'

export async function getDashboard(): Promise<DashboardData> {
  const payload = await getJson<ProjectionEnvelope<DashboardData>>('/api/v1/projections/dashboard')
  return payload.data
}

export async function getInbox(): Promise<InboxData> {
  const payload = await getJson<ProjectionEnvelope<InboxData>>('/api/v1/projections/inbox')
  return payload.data
}

export async function getRuntimeProvider(): Promise<RuntimeProviderData> {
  const payload = await getJson<ProjectionEnvelope<RuntimeProviderData>>('/api/v1/projections/runtime-provider')
  return payload.data
}

export async function getWorkforce(): Promise<WorkforceData> {
  const payload = await getJson<ProjectionEnvelope<WorkforceData>>('/api/v1/projections/workforce')
  return payload.data
}

export async function getReviewRoom(reviewPackId: string): Promise<ReviewRoomData> {
  const payload = await getJson<ProjectionEnvelope<ReviewRoomData>>(
    `/api/v1/projections/review-room/${reviewPackId}`,
  )
  return payload.data
}

export async function getDependencyInspector(workflowId: string): Promise<DependencyInspectorData> {
  const payload = await getJson<ProjectionEnvelope<DependencyInspectorData>>(
    `/api/v1/projections/workflows/${workflowId}/dependency-inspector`,
  )
  return payload.data
}

export async function getIncidentDetail(incidentId: string): Promise<IncidentDetailData> {
  const payload = await getJson<ProjectionEnvelope<IncidentDetailData>>(
    `/api/v1/projections/incidents/${incidentId}`,
  )
  return payload.data
}

export async function getDeveloperInspector(reviewPackId: string): Promise<DeveloperInspectorData> {
  const payload = await getJson<ProjectionEnvelope<DeveloperInspectorData>>(
    `/api/v1/projections/review-room/${reviewPackId}/developer-inspector`,
  )
  return payload.data
}
