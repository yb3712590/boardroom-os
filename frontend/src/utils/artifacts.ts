export function isArtifactRef(value: string | null | undefined): value is string {
  return typeof value === 'string' && value.startsWith('art://')
}

export function artifactRefFilename(artifactRef: string): string {
  const trimmed = artifactRef.trim()
  if (!trimmed) {
    return ''
  }
  const slashIndex = trimmed.lastIndexOf('/')
  return slashIndex >= 0 ? trimmed.slice(slashIndex + 1) : trimmed
}
