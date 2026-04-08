import { useEffect } from 'react'

import { AnimatePresence, motion } from 'framer-motion'

type ToastProps = {
  message: string
  variant: 'success' | 'error' | 'info'
  onDismiss: () => void
}

export function Toast({ message, variant, onDismiss }: ToastProps) {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, 5000)
    return () => window.clearTimeout(timer)
  }, [onDismiss])

  return (
    <AnimatePresence>
      <motion.div
        key={message}
        className={`shared-toast shared-toast-${variant}`}
        initial={{ opacity: 0, x: 24 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: 24 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        role="status"
      >
        <span>{message}</span>
        <button type="button" className="ghost-button" onClick={onDismiss} aria-label="关闭消息">
          关闭
        </button>
      </motion.div>
    </AnimatePresence>
  )
}
