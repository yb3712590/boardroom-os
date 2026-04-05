import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { EventTicker } from '../../../components/events/EventTicker'

describe('EventTicker', () => {
  it('renders a loading skeleton instead of empty-state copy while events are loading', () => {
    const { container } = render(<EventTicker events={[]} loading={true} />)

    expect(screen.queryByText('No recent events were emitted.')).not.toBeInTheDocument()
    expect(container.querySelector('.loading-skeleton')).not.toBeNull()
  })
})
