type ProfileSummaryProps = {
  label?: string
  summary?: string | null
  skillProfile: Record<string, string>
  personalityProfile: Record<string, string>
  aestheticProfile: Record<string, string>
}

function humanize(value: string) {
  return value.replaceAll('_', ' ')
}

function formatGroup(profile: Record<string, string>) {
  return Object.entries(profile)
    .map(([key, value]) => `${humanize(key)}: ${humanize(value)}`)
    .join(' | ')
}

export function ProfileSummary({
  label,
  summary,
  skillProfile,
  personalityProfile,
  aestheticProfile,
}: ProfileSummaryProps) {
  const hasProfiles =
    Object.keys(skillProfile).length > 0 ||
    Object.keys(personalityProfile).length > 0 ||
    Object.keys(aestheticProfile).length > 0

  if (!hasProfiles) {
    return null
  }

  const effectiveSummary =
    summary?.trim() ||
    [
      formatGroup(skillProfile),
      formatGroup(personalityProfile),
      formatGroup(aestheticProfile),
    ]
      .filter(Boolean)
      .join(' / ')

  return (
    <div className="profile-summary-card">
      {label ? <strong className="profile-summary-title">{label}</strong> : null}
      <p className="profile-summary-copy">{effectiveSummary}</p>
      <dl className="profile-summary-grid">
        <div>
          <dt>技能</dt>
          <dd>{formatGroup(skillProfile)}</dd>
        </div>
        <div>
          <dt>性格</dt>
          <dd>{formatGroup(personalityProfile)}</dd>
        </div>
        <div>
          <dt>审美</dt>
          <dd>{formatGroup(aestheticProfile)}</dd>
        </div>
      </dl>
    </div>
  )
}
