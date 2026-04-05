import type { ReactNode } from 'react'

type ThreeColumnLayoutProps = {
  left: ReactNode
  center: ReactNode
  right: ReactNode
}

export function ThreeColumnLayout({ left, center, right }: ThreeColumnLayoutProps) {
  return (
    <main className="boardroom-main" id="boardroom-main-content" tabIndex={-1}>
      {left}
      {center}
      {right}
    </main>
  )
}
