import type { ReactNode } from 'react'

type ThreeColumnLayoutProps = {
  left: ReactNode
  center: ReactNode
  right: ReactNode
}

export function ThreeColumnLayout({ left, center, right }: ThreeColumnLayoutProps) {
  return (
    <div className="boardroom-main">
      {left}
      {center}
      {right}
    </div>
  )
}
