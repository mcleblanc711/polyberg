export type CopyOutcome = 'copied' | 'error'

export interface CopyDeps {
  // Native (Electron main-process) clipboard write, preferred when available.
  writeClipboard?: (text: string) => Promise<void>
  // Browser fallback (navigator.clipboard.writeText).
  navigatorWrite?: (text: string) => Promise<void>
}

/**
 * Copy the full rendered packet markdown to the clipboard.
 *
 * Tries the native bridge first, then the browser clipboard API. Returns
 * 'copied' on the first success and 'error' only if every available path
 * fails — it never silently fails, and the caller keeps the text visible for
 * manual copy on 'error'.
 */
export const copyPacket = async (text: string, deps: CopyDeps): Promise<CopyOutcome> => {
  const attempts: Array<(t: string) => Promise<void>> = []
  if (deps.writeClipboard) attempts.push(deps.writeClipboard)
  if (deps.navigatorWrite) attempts.push(deps.navigatorWrite)

  for (const attempt of attempts) {
    try {
      await attempt(text)
      return 'copied'
    } catch {
      // Try the next available clipboard path.
    }
  }
  return 'error'
}
