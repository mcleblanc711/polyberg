import { Component, Suspense, lazy, useState, type ReactNode } from 'react'
import { ResearchProvider } from './research/ResearchProvider'
import { ResearchScreen } from './research/ResearchScreen'

const LegacyWorkspace = lazy(() => import('./LegacyWorkspace'))
class LegacyError extends Component<{ children: ReactNode }, { error: string }> {
  state = { error: '' }
  static getDerivedStateFromError(error: Error): { error: string } { return { error: error.message } }
  render(): ReactNode {
    return this.state.error ? <p role="alert">Legacy workspace failed: {this.state.error}</p> : this.props.children
  }
}
export function WorkspaceApp(): JSX.Element {
  const [workspace, setWorkspace] = useState<'research' | 'legacy'>('research')
  const [error, setError] = useState('')
  const select = async (next: 'research' | 'legacy'): Promise<void> => {
    try { await window.research.selectWorkspace(next); setWorkspace(next); setError('') }
    catch { setError('Could not switch workspace') }
  }
  return <div className="workspace-shell">
    <div className="workspace-switch">
      <strong>polyberg / terminal</strong>
      <button aria-pressed={workspace === 'research'} onClick={() => void select('research')}>Market research</button>
      <button aria-pressed={workspace === 'legacy'} onClick={() => void select('legacy')}>Legacy portfolio</button>
      <span>{workspace === 'research' ? 'PUBLIC DATA · LOCAL RESEARCH' : 'LEGACY WORKSPACE'}</span>
      {error && <span role="alert">{error}</span>}
    </div>
    <div className="workspace-body">{workspace === 'research'
      ? <ResearchProvider><ResearchScreen /></ResearchProvider>
      : <LegacyError><Suspense fallback={<p>Loading legacy workspace…</p>}><LegacyWorkspace /></Suspense></LegacyError>}
    </div>
  </div>
}
