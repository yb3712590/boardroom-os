import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { RuntimeStatusCard } from '../../../components/dashboard/RuntimeStatusCard'

describe('RuntimeStatusCard', () => {
  it('shows provider-required unavailable copy and health details', () => {
    render(
      <RuntimeStatusCard
        effectiveMode="PROVIDER_REQUIRED_UNAVAILABLE"
        providerLabel="Provider required"
        model={null}
        workerCount={1}
        healthSummary="UNAVAILABLE"
        reason="No live provider is configured for runtime execution."
        onOpenSettings={vi.fn()}
      />,
    )

    expect(screen.getByText('Provider required')).toBeInTheDocument()
    expect(screen.getByText('No live provider is configured for runtime execution.')).toBeInTheDocument()
    expect(screen.getByText('No live provider configured')).toBeInTheDocument()
    expect(screen.getByText('UNAVAILABLE')).toBeInTheDocument()
  })
})
