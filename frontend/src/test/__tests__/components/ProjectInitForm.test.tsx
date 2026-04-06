import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ProjectInitForm } from '../../../components/dashboard/ProjectInitForm'

describe('ProjectInitForm', () => {
  it('disables submit when the north star goal is empty', async () => {
    const user = userEvent.setup()
    render(<ProjectInitForm submitting={false} onSubmit={vi.fn()} />)

    const goalField = screen.getByLabelText('North star goal')
    const submitButton = screen.getByRole('button', { name: 'Launch to first review' })

    await user.clear(goalField)

    expect(submitButton).toBeDisabled()
  })

  it('normalizes hard constraints before submitting', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)

    render(<ProjectInitForm submitting={false} onSubmit={onSubmit} />)

    await user.clear(screen.getByLabelText('North star goal'))
    await user.type(screen.getByLabelText('North star goal'), 'Stabilize the review shell')
    await user.clear(screen.getByLabelText('Hard constraints'))
    await user.type(screen.getByLabelText('Hard constraints'), 'Keep auditability{enter}{enter}Stay local-first')
    await user.clear(screen.getByLabelText('Budget cap'))
    await user.type(screen.getByLabelText('Budget cap'), '1200')

    await user.click(screen.getByRole('button', { name: 'Launch to first review' }))

    expect(onSubmit).toHaveBeenCalledWith({
      northStarGoal: 'Stabilize the review shell',
      hardConstraints: ['Keep auditability', 'Stay local-first'],
      budgetCap: 1200,
      forceRequirementElicitation: false,
    })
  })

  it('submits force requirement elicitation when the toggle is enabled', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)

    render(<ProjectInitForm submitting={false} onSubmit={onSubmit} />)

    await user.click(screen.getByLabelText('Route through requirement elicitation first'))
    await user.click(screen.getByRole('button', { name: 'Launch to first review' }))

    expect(onSubmit).toHaveBeenCalledWith({
      northStarGoal: 'Ship the thinnest governance shell from dashboard to review room.',
      hardConstraints: ['Keep governance explicit.', 'Do not move workflow truth into the browser.'],
      budgetCap: 500000,
      forceRequirementElicitation: true,
    })
  })
})
