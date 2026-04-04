import type { ReactNode } from 'react'

type BadgeProps = {
  variant: 'info' | 'warning' | 'critical' | 'success' | 'muted'
  children: ReactNode
}

export function Badge({ variant, children }: BadgeProps) {
  return <span className={`shared-badge shared-badge-${variant}`}>{children}</span>
}
