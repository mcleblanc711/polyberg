const legacy = new Set<number>()
export const selectWorkspace = (id: number, value: unknown): void => {
  if (value !== 'research' && value !== 'legacy') throw new Error('Unknown workspace')
  if (value === 'legacy') legacy.add(id)
  else legacy.delete(id)
}
export const requireLegacy = (id: number): void => {
  if (!legacy.has(id)) throw new Error('Select the legacy workspace explicitly to use account features')
}
export const clearWorkspace = (id: number): void => { legacy.delete(id) }
