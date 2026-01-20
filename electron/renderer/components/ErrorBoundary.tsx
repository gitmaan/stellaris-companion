import React from 'react'

type ErrorBoundaryProps = {
  children: React.ReactNode
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
  }

  handleReload = () => {
    window.location.reload()
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children
    }

    return (
      <div style={{ padding: 24, fontFamily: 'system-ui, sans-serif' }}>
        <h2>Something went wrong</h2>
        <p>The UI encountered an unexpected error.</p>
        <button onClick={this.handleReload}>Reload</button>
        {this.state.errorMessage && (
          <pre style={{ marginTop: 16, whiteSpace: 'pre-wrap' }}>
            {this.state.errorMessage}
            {this.state.errorStack ? `\n\n${this.state.errorStack}` : ''}
          </pre>
        )}
      </div>
    )
  }
}

export default ErrorBoundary

