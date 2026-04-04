import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterAll, afterEach, describe, expect, it, vi } from 'vitest'

import { ErrorBoundary } from '../../../components/shared/ErrorBoundary'

function Crashable({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error('boom')
  }
  return <div>Recovered child</div>
}

describe('ErrorBoundary', () => {
  const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

  afterAll(() => {
    consoleErrorSpy.mockRestore()
  })

  afterEach(() => {
    consoleErrorSpy.mockClear()
  })

  it('shows fallback on render error and recovers after retry', async () => {
    const user = userEvent.setup()

    const { rerender } = render(
      <ErrorBoundary>
        <Crashable shouldThrow />
      </ErrorBoundary>,
    )

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Boardroom page crashed.')).toBeInTheDocument()

    rerender(
      <ErrorBoundary>
        <Crashable shouldThrow={false} />
      </ErrorBoundary>,
    )

    await user.click(screen.getByRole('button', { name: 'Retry' }))

    expect(screen.getByText('Recovered child')).toBeInTheDocument()
  })
})
