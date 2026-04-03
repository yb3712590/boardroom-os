import { useEffect, type ReactNode } from 'react'

import { AnimatePresence, motion } from 'framer-motion'

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
  useEffect(() => {
    if (!isOpen) {
      return
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  return (
    <AnimatePresence>
      {isOpen ? (
        <motion.aside
          className="review-room-drawer drawer-root"
          initial={{ opacity: 0, x: 48 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 48 }}
          transition={{ duration: 0.24, ease: 'easeOut' }}
          aria-modal="true"
          role="dialog"
          aria-label={title}
        >
          <div className="review-room-backdrop drawer-backdrop" onClick={onClose} aria-hidden="true" />
          <motion.section
            className="review-room-panel drawer-panel"
            style={{ width }}
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 18 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
          >
            <header className="review-room-header drawer-header">
              <div>
                {subtitle ? <p className="eyebrow">{subtitle}</p> : null}
                <h2>{title}</h2>
              </div>
              <button type="button" className="ghost-button" onClick={onClose} aria-label={`Close ${title}`}>
                Close
              </button>
            </header>
            <div className="drawer-body">{children}</div>
          </motion.section>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  )
}
