import React from 'react'

type ErrorBoundaryProps = {
  children: React.ReactNode
  onError?: (error: Error) => void
}

type ErrorBoundaryState = {
  hasError: boolean
  errorMessage?: string
  errorStack?: string
}

class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    if (error instanceof Error) {
      return { hasError: true, errorMessage: error.message, errorStack: error.stack }
    }
    return { hasError: true, errorMessage: String(error) }
  }

  componentDidCatch(error: unknown) {
    console.error('Renderer error:', error)
    // Notify parent for toast prompt
    if (error instanceof Error && this.props.onError) {
      this.props.onError(error)
    }
  }

  handleReload = () => {
    window.location.reload()
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children
    }

    return (
      <div className="p-6 font-sans bg-bg-primary min-h-screen">
        <div className="max-w-lg mx-auto pt-12">
          {/* Header */}
          <div className="flex items-center gap-3 mb-4">
            <span className="text-accent-red text-2xl">⚠</span>
            <h2 className="text-xl text-accent-red font-semibold">Anomaly Detected</h2>
          </div>

          <p className="text-text-secondary mb-6">
            An unexpected error has disrupted operations.
          </p>

          {/* Action buttons */}
          <div className="flex gap-3 mb-6">
            <button
              onClick={this.handleReload}
              className="px-5 py-2.5 border border-accent-cyan/50 rounded text-accent-cyan hover:bg-accent-cyan/20 transition-colors font-medium"
            >
              Reload
            </button>
          </div>

          {/* Error details */}
          {this.state.errorMessage && (
            <div className="stellaris-panel rounded-lg p-4">
              <div className="text-xs text-text-secondary uppercase tracking-wider mb-2">
                Error Details
              </div>
              <pre className="text-xs text-text-secondary font-mono whitespace-pre-wrap overflow-auto max-h-[200px]">
                {this.state.errorMessage}
                {this.state.errorStack ? `\n\n${this.state.errorStack}` : ''}
              </pre>
            </div>
          )}
        </div>
      </div>
    )
  }
}

export default ErrorBoundary
