import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { RuntimeStatusCard } from '../../../components/dashboard/RuntimeStatusCard'

describe('RuntimeStatusCard', () => {
  it('shows deterministic fallback copy and health details', () => {
    render(
      <RuntimeStatusCard
        effectiveMode="LOCAL_DETERMINISTIC"
        providerLabel="Local deterministic"
        model={null}
        workerCount={1}
        healthSummary="LOCAL_ONLY"
        reason="Runtime is using the local deterministic path."
        onOpenSettings={vi.fn()}
      />,
    )

    expect(screen.getByText('Local deterministic')).toBeInTheDocument()
    expect(screen.getByText('Runtime is using the local deterministic path.')).toBeInTheDocument()
    expect(screen.getByText('Deterministic local runtime')).toBeInTheDocument()
    expect(screen.getByText('LOCAL_ONLY')).toBeInTheDocument()
  })
})
