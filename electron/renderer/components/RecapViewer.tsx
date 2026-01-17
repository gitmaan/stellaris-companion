interface RecapViewerProps {
  recap: string | null
  loading?: boolean
}

function RecapViewer({ recap, loading }: RecapViewerProps) {
  if (loading) {
    return <div className="recap-viewer loading">Generating recap...</div>
  }

  if (!recap) {
    return <div className="recap-viewer empty">Select a session and generate a recap.</div>
  }

  return (
    <div className="recap-viewer">
      <pre className="recap-content">{recap}</pre>
    </div>
  )
}

export default RecapViewer
