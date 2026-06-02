import { describe, expect, it, vi } from 'vitest'
import { copyPacket } from './copyPacket'

const GPT_PACKET = '# Polyberg Current Research Packet — GPT Source\n\nbody'
const CLAUDE_PACKET = '# Polyberg Current Research Packet — Claude Source\n\nbody'

describe('copyPacket', () => {
  it('passes the exact rendered GPT packet text to the native clipboard', async () => {
    const writeClipboard = vi.fn().mockResolvedValue(undefined)
    const navigatorWrite = vi.fn().mockResolvedValue(undefined)

    const outcome = await copyPacket(GPT_PACKET, { writeClipboard, navigatorWrite })

    expect(outcome).toBe('copied')
    expect(writeClipboard).toHaveBeenCalledWith(GPT_PACKET)
    // Native path succeeded, so the browser fallback is not used.
    expect(navigatorWrite).not.toHaveBeenCalled()
  })

  it('passes the exact rendered Claude packet text to the native clipboard', async () => {
    const writeClipboard = vi.fn().mockResolvedValue(undefined)

    const outcome = await copyPacket(CLAUDE_PACKET, { writeClipboard })

    expect(outcome).toBe('copied')
    expect(writeClipboard).toHaveBeenCalledWith(CLAUDE_PACKET)
  })

  it('falls back to the browser clipboard when the native bridge fails', async () => {
    const writeClipboard = vi.fn().mockRejectedValue(new Error('no bridge'))
    const navigatorWrite = vi.fn().mockResolvedValue(undefined)

    const outcome = await copyPacket(GPT_PACKET, { writeClipboard, navigatorWrite })

    expect(outcome).toBe('copied')
    expect(navigatorWrite).toHaveBeenCalledWith(GPT_PACKET)
  })

  it('reports an error (never silently fails) when every clipboard path fails', async () => {
    const writeClipboard = vi.fn().mockRejectedValue(new Error('no bridge'))
    const navigatorWrite = vi.fn().mockRejectedValue(new Error('blocked'))

    const outcome = await copyPacket(GPT_PACKET, { writeClipboard, navigatorWrite })

    expect(outcome).toBe('error')
  })
})
