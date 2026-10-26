import { describe, expect, it } from 'vitest'
import { clearWorkspace, requireLegacy, selectWorkspace } from './workspaceAccess'
describe('explicit legacy selection', () => {
  it('denies legacy access at startup and after returning to research', () => {
    expect(() => requireLegacy(71)).toThrow('Select the legacy workspace')
    selectWorkspace(71, 'legacy')
    expect(() => requireLegacy(71)).not.toThrow()
    expect(() => requireLegacy(72)).toThrow()
    selectWorkspace(71, 'research')
    expect(() => requireLegacy(71)).toThrow()
  })
  it('clears permission when a window closes', () => {
    selectWorkspace(73, 'legacy'); clearWorkspace(73)
    expect(() => requireLegacy(73)).toThrow()
    expect(() => selectWorkspace(73, 'account')).toThrow()
  })
})
