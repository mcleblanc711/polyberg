import React from 'react'
import { renderToString } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
vi.mock('../LegacyWorkspace', () => { throw new Error('Legacy imported at research startup') })
import { WorkspaceApp } from '../WorkspaceApp'

describe('research desktop startup', () => {
  it('renders an empty research workspace without importing legacy', () => {
    const html = renderToString(React.createElement(WorkspaceApp))
    expect(html).toContain('Start with a market question.')
    expect(html).toContain('No account connection is needed.')
    expect(html).toContain('Follow URL / ID')
    expect(html).not.toContain('Loading legacy workspace')
  })
})
