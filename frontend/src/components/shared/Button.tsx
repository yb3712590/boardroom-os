import type { ButtonHTMLAttributes, ReactNode } from 'react'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

type ButtonProps = {
  variant: ButtonVariant
  loading?: boolean
  children: ReactNode
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'>

function variantClassName(variant: ButtonVariant) {
  switch (variant) {
    case 'primary':
      return 'primary-button'
    case 'secondary':
      return 'secondary-button'
    case 'danger':
      return 'danger-button'
    case 'ghost':
    default:
      return 'ghost-button'
  }
}

export function Button({ variant, loading = false, className, children, disabled, ...props }: ButtonProps) {
  const classes = [variantClassName(variant), className].filter(Boolean).join(' ')

  return (
    <button {...props} className={classes} disabled={disabled || loading}>
      {children}
    </button>
  )
}
