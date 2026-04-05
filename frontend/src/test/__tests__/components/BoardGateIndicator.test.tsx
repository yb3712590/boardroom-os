import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { BoardGateIndicator } from '../../../components/dashboard/BoardGateIndicator'

describe('BoardGateIndicator', () => {
  it('shows armed board state when approvals are waiting', () => {
    const { container } = render(<BoardGateIndicator approvalsPending={2} />)

    expect(screen.getByText('Board Gate armed')).toBeInTheDocument()
    expect(screen.getByText('2 approvals pending')).toBeInTheDocument()
    expect(container.querySelector('.board-chip.is-armed')).not.toBeNull()
  })

  it('shows clear board state when no approvals are waiting', () => {
    const { container } = render(<BoardGateIndicator approvalsPending={0} />)

    expect(screen.getByText('Board Gate clear')).toBeInTheDocument()
    expect(screen.getByText('No approvals pending')).toBeInTheDocument()
    expect(container.querySelector('.board-chip.is-clear')).not.toBeNull()
  })
})
