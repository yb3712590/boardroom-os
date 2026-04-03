import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterAll, afterEach, describe, expect, it, vi } from 'vitest'

import { ErrorBoundary } from '../../../components/shared/ErrorBoundary'

let shouldThrow = false

function CrashOnce() {
  if (shouldThrow) {
    shouldThrow = false
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
    shouldThrow = false
    consoleErrorSpy.mockClear()
  })

  it('shows fallback on render error and recovers after retry', async () => {
    shouldThrow = true
    const user = userEvent.setup()

    render(
      <ErrorBoundary>
        <CrashOnce />
      </ErrorBoundary>,
    )

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Boardroom page crashed.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Retry' }))

    expect(screen.getByText('Recovered child')).toBeInTheDocument()
  })
})
