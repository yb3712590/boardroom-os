import { Component, type ReactNode } from 'react'

type ErrorBoundaryProps = {
  children: ReactNode
  fallback?: ReactNode
}

type ErrorBoundaryState = {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    hasError: false,
    error: null,
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return {
      hasError: true,
      error,
    }
  }

  private handleRetry = () => {
    this.setState({
      hasError: false,
      error: null,
    })
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <section className="shell-error" role="alert">
            <strong>页面渲染失败。</strong>
            <p>{this.state.error?.message ?? '发生了未预期的渲染错误。'}</p>
            <button type="button" className="secondary-button" onClick={this.handleRetry}>
              重试
            </button>
          </section>
        )
      )
    }

    return this.props.children
  }
}
