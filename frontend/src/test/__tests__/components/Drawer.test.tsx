import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

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

    fireEvent.keyDown(window, { key: 'Escape' })

    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
