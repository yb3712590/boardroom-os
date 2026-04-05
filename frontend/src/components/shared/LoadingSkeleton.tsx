type LoadingSkeletonProps = {
  lines?: number
  className?: string
}

export function LoadingSkeleton({ lines = 3, className }: LoadingSkeletonProps) {
  return (
    <div className={['loading-skeleton', className].filter(Boolean).join(' ')} aria-hidden="true">
      {Array.from({ length: lines }).map((_, index) => (
        <span
          key={index}
          className="loading-skeleton-line"
          style={{ width: `${Math.max(56, 100 - index * 12)}%` }}
        />
      ))}
    </div>
  )
}
