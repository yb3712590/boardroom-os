import { useEffect, useLayoutEffect, useRef, type ReactNode } from 'react'

type DrawerProps = {
  isOpen: boolean
  onClose: () => void
  title: string
  subtitle?: string
  width?: string
  children: ReactNode
}

export function Drawer({
  isOpen,
  onClose,
  title,
  subtitle,
  width = '680px',
  children,
}: DrawerProps) {
  const panelRef = useRef<HTMLElement | null>(null)
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)
  const lastFocusedElementRef = useRef<HTMLElement | null>(null)
  const bodyOverflowRef = useRef<string>('')

  useLayoutEffect(() => {
    if (!isOpen) {
      return
    }

    lastFocusedElementRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    bodyOverflowRef.current = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeButtonRef.current?.focus()

    return () => {
      document.body.style.overflow = bodyOverflowRef.current
    }
  }, [isOpen])

  useEffect(() => {
    if (isOpen || lastFocusedElementRef.current == null) {
      return
    }

    const timer = setTimeout(() => {
      lastFocusedElementRef.current?.focus()
    }, 0)

    return () => clearTimeout(timer)
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) {
      return
    }

    const getFocusableElements = () => {
      if (!panelRef.current) {
        return []
      }

      return Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => !element.hasAttribute('disabled'))
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
        return
      }

      if (event.key !== 'Tab') {
        return
      }

      const focusableElements = getFocusableElements()
      if (focusableElements.length === 0) {
        event.preventDefault()
        closeButtonRef.current?.focus()
        return
      }

      const firstElement = focusableElements[0]
      const lastElement = focusableElements[focusableElements.length - 1]
      const activeElement = document.activeElement

      if (event.shiftKey) {
        if (activeElement === firstElement || !panelRef.current?.contains(activeElement)) {
          event.preventDefault()
          lastElement.focus()
        }
        return
      }

      if (activeElement === lastElement) {
        event.preventDefault()
        firstElement.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) {
    return null
  }

  return (
    <aside
      className="review-room-drawer drawer-root"
      aria-modal="true"
      role="dialog"
      aria-label={title}
    >
      <div className="review-room-backdrop drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <section className="review-room-panel drawer-panel" style={{ width }} ref={panelRef}>
        <header className="review-room-header drawer-header">
          <div>
            {subtitle ? <p className="eyebrow">{subtitle}</p> : null}
            <h2>{title}</h2>
          </div>
          <button
            type="button"
            className="ghost-button"
            onClick={onClose}
            aria-label={`关闭${title}`}
            ref={closeButtonRef}
          >
            关闭
          </button>
        </header>
        <div className="drawer-body">{children}</div>
      </section>
    </aside>
  )
}
