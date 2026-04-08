import { useEffect, useState } from 'react'

import { getArtifactMetadata, getArtifactPreview } from '../../api/artifacts'
import { ApiError } from '../../api/client'
import type { ArtifactMetadata, ArtifactPreview } from '../../types/artifacts'
import { artifactRefFilename } from '../../utils/artifacts'
import { Drawer } from '../shared/Drawer'

type ArtifactPreviewDrawerProps = {
  isOpen: boolean
  artifactRef: string | null
  onClose: () => void
}

type ArtifactPreviewState = {
  loading: boolean
  error: string | null
  metadata: ArtifactMetadata | null
  preview: ArtifactPreview | null
}

const INITIAL_STATE: ArtifactPreviewState = {
  loading: false,
  error: null,
  metadata: null,
  preview: null,
}

function readApiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = error.detail
    if (
      detail != null &&
      typeof detail === 'object' &&
      'detail' in detail &&
      typeof detail.detail === 'string' &&
      detail.detail.trim().length > 0
    ) {
      return detail.detail
    }
  }
  return error instanceof Error ? error.message : '加载所选产物失败。'
}

function renderInlineMedia(metadata: ArtifactMetadata, preview: ArtifactPreview) {
  const contentUrl = preview.content_url ?? metadata.content_url
  if (!contentUrl) {
    return <p className="muted-copy">该产物暂不支持内联预览。</p>
  }
  if ((preview.media_type ?? metadata.media_type ?? '').includes('pdf')) {
    return (
      <iframe
        className="artifact-preview-frame"
        src={contentUrl}
        title={`预览 ${artifactRefFilename(metadata.artifact_ref)}`}
      />
    )
  }

  return (
    <img
      className="artifact-preview-image"
      src={contentUrl}
      alt={artifactRefFilename(metadata.artifact_ref) || metadata.artifact_ref}
    />
  )
}

export function ArtifactPreviewDrawer({ isOpen, artifactRef, onClose }: ArtifactPreviewDrawerProps) {
  const [state, setState] = useState<ArtifactPreviewState>(INITIAL_STATE)

  useEffect(() => {
    if (!isOpen || artifactRef == null) {
      setState(INITIAL_STATE)
      return
    }

    let cancelled = false
    setState({
      loading: true,
      error: null,
      metadata: null,
      preview: null,
    })

    void Promise.all([getArtifactMetadata(artifactRef), getArtifactPreview(artifactRef)])
      .then(([metadata, preview]) => {
        if (cancelled) {
          return
        }
        setState({
          loading: false,
          error: null,
          metadata,
          preview,
        })
      })
      .catch((error) => {
        if (cancelled) {
          return
        }
        setState({
          loading: false,
          error: readApiErrorMessage(error),
          metadata: null,
          preview: null,
        })
      })

    return () => {
      cancelled = true
    }
  }, [artifactRef, isOpen])

  const metadata = state.metadata
  const preview = state.preview
  const artifactTitle = metadata ? artifactRefFilename(metadata.artifact_ref) || metadata.artifact_ref : '产物预览'

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="产物预览" subtitle={artifactTitle} width="760px">
      {state.loading ? (
        <div className="review-room-state">正在加载所选产物...</div>
      ) : state.error ? (
        <div className="review-room-state review-room-error">{state.error}</div>
      ) : metadata == null || preview == null ? (
        <div className="review-room-state">该引用暂无可用产物预览。</div>
      ) : (
        <div className="review-room-content">
          <section className="review-room-overview artifact-preview-overview">
            <div>
              <span className="eyebrow">产物引用</span>
              <p>{metadata.artifact_ref}</p>
            </div>
            <div>
              <span className="eyebrow">路径</span>
              <p>{metadata.path}</p>
            </div>
            <div>
              <span className="eyebrow">预览类型</span>
              <p>{preview.preview_kind}</p>
            </div>
          </section>

          <section className="review-room-column artifact-preview-panel">
            {preview.preview_kind === 'JSON' ? (
              <pre className="artifact-preview-code">{JSON.stringify(preview.json_content, null, 2)}</pre>
            ) : null}
            {preview.preview_kind === 'TEXT' ? (
              <pre className="artifact-preview-code">{preview.text_content ?? ''}</pre>
            ) : null}
            {preview.preview_kind === 'INLINE_MEDIA' ? renderInlineMedia(metadata, preview) : null}
            {preview.preview_kind === 'DOWNLOAD_ONLY' ? (
              <div className="artifact-preview-download">
                <p>可从本地后端下载该产物。</p>
                <a
                  className="secondary-button artifact-preview-link"
                  href={preview.download_url ?? metadata.download_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  下载产物
                </a>
              </div>
            ) : null}
          </section>
        </div>
      )}
    </Drawer>
  )
}
