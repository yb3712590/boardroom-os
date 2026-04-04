type LoadingSkeletonProps = {
  lines?: number
}

export function LoadingSkeleton({ lines = 3 }: LoadingSkeletonProps) {
  return (
    <div className="loading-skeleton" aria-hidden="true">
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
