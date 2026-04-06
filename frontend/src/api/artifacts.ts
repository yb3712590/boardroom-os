import { getJson } from './client'
import type {
  ArtifactMetadata,
  ArtifactMetadataEnvelope,
  ArtifactPreview,
  ArtifactPreviewEnvelope,
} from '../types/artifacts'

export async function getArtifactMetadata(artifactRef: string): Promise<ArtifactMetadata> {
  const payload = await getJson<ArtifactMetadataEnvelope>(
    `/api/v1/artifacts/by-ref?artifact_ref=${encodeURIComponent(artifactRef)}`,
  )
  return payload.data
}

export async function getArtifactPreview(artifactRef: string): Promise<ArtifactPreview> {
  const payload = await getJson<ArtifactPreviewEnvelope>(
    `/api/v1/artifacts/preview?artifact_ref=${encodeURIComponent(artifactRef)}`,
  )
  return payload.data
}
