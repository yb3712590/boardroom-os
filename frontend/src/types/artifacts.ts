export type ArtifactMetadata = {
  artifact_ref: string
  workflow_id: string
  ticket_id: string
  node_id: string
  path: string
  kind: string
  media_type: string | null
  preview_kind: string | null
  display_hint: string | null
  status: string
  materialization_status: string
  lifecycle_status: string
  retention_class: string
  retention_class_source: string | null
  retention_ttl_sec: number | null
  retention_policy_source: string | null
  expires_at: string | null
  deleted_at: string | null
  deleted_by: string | null
  delete_reason: string | null
  storage_backend: string
  storage_object_key: string | null
  storage_delete_status: string
  storage_delete_error: string | null
  storage_deleted_at: string | null
  size_bytes: number | null
  content_hash: string | null
  created_at: string
  content_url: string
  download_url: string
  preview_url: string
}

export type ArtifactMetadataEnvelope = {
  data: ArtifactMetadata
}

export type ArtifactPreview = {
  artifact_ref: string
  preview_kind: string
  media_type: string | null
  lifecycle_status: string
  content_url: string | null
  download_url: string | null
  json_content: unknown
  text_content: string | null
}

export type ArtifactPreviewEnvelope = {
  data: ArtifactPreview
}
