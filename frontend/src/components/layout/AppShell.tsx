import type { ReactNode } from 'react'

type AppShellProps = {
  children: ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="boardroom-app">
      <div className="boardroom-shell">{children}</div>
    </div>
  )
}
