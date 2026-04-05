import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { useState } from 'react'

import { Drawer } from '../../../components/shared/Drawer'

describe('Drawer', () => {
  it('renders content and closes when backdrop is clicked', () => {
    const onClose = vi.fn()
    const { container } = render(
      <Drawer isOpen onClose={onClose} title="Test Drawer" subtitle="Overlay">
        <div>Drawer content</div>
      </Drawer>,
    )

    expect(screen.getByRole('dialog', { name: 'Test Drawer' })).toBeInTheDocument()
    expect(screen.getByText('Drawer content')).toBeInTheDocument()

    const backdrop = container.querySelector('.drawer-backdrop')
    expect(backdrop).not.toBeNull()
    fireEvent.click(backdrop as Element)

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes when Escape is pressed', () => {
    const onClose = vi.fn()

    render(
      <Drawer isOpen onClose={onClose} title="Escape Drawer">
        <div>Drawer content</div>
      </Drawer>,
    )

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('moves initial focus into the drawer, traps tab order, and restores focus when closed', async () => {
    const user = userEvent.setup()

    function DrawerHarness() {
      const [open, setOpen] = useState(false)

      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Open drawer
          </button>
          <Drawer isOpen={open} onClose={() => setOpen(false)} title="Focus Drawer">
            <button type="button">First action</button>
            <button type="button">Second action</button>
          </Drawer>
        </>
      )
    }

    render(<DrawerHarness />)

    const openButton = screen.getByRole('button', { name: 'Open drawer' })
    openButton.focus()

    await user.click(openButton)

    const closeButton = screen.getByRole('button', { name: /close focus drawer/i })
    const firstAction = screen.getByRole('button', { name: 'First action' })
    const secondAction = screen.getByRole('button', { name: 'Second action' })

    expect(closeButton).toHaveFocus()

    await user.tab()
    expect(firstAction).toHaveFocus()

    await user.tab()
    expect(secondAction).toHaveFocus()

    await user.tab()
    expect(closeButton).toHaveFocus()

    await user.tab({ shift: true })
    expect(secondAction).toHaveFocus()

    await user.keyboard('{Escape}')

    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Focus Drawer' })).not.toBeInTheDocument(),
    )
    expect(openButton).toHaveFocus()
  })
})
