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
            <strong>Boardroom page crashed.</strong>
            <p>{this.state.error?.message ?? 'An unexpected render error occurred.'}</p>
            <button type="button" className="secondary-button" onClick={this.handleRetry}>
              Retry
            </button>
          </section>
        )
      )
    }

    return this.props.children
  }
}
