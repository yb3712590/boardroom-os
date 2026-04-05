import type { ReactNode } from 'react'

type AppShellProps = {
  children: ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="boardroom-app">
      <a className="skip-link" href="#boardroom-main-content">
        Skip to main content
      </a>
      <div className="boardroom-shell">{children}</div>
    </div>
  )
}
