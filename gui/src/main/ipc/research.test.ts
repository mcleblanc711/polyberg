import { EventEmitter } from 'events'
import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({spawn: vi.fn(), watch: vi.fn()}))
vi.mock('child_process', () => ({spawn: mocks.spawn}))
vi.mock('chokidar', () => ({default: {watch: mocks.watch}}))
vi.mock('./repo', () => ({REPO_ROOT: '/synthetic-repo'}))
import { runResearch, researchWatchPaths, startResearchWatch, stopResearchWatch } from './research'
import type { WebContents } from 'electron'

describe('research subprocess and watcher isolation', () => {
  beforeEach(() => { vi.clearAllMocks() })
  it('passes a JSON request over stdin and a fixed public CLI namespace', async () => {
    const child = Object.assign(new EventEmitter(), {
      stdout: new EventEmitter(), stderr: {resume: vi.fn()},
      stdin: Object.assign(new EventEmitter(), {end: vi.fn()}), kill: vi.fn()
    })
    mocks.spawn.mockReturnValue(child)
    process.env.POLYMARKET_PROXY_WALLET = 'SYNTHETIC_SECRET'
    process.env.CLOB_API_KEY = 'SYNTHETIC_SECRET'
    const request = {operation: 'follow', reference: 'market:900001'} as const
    const result = runResearch(request)
    const [, args, options] = mocks.spawn.mock.calls[0]
    expect(args).toEqual(['-m', 'polyberg.cli', '--db', expect.any(String), 'research', 'rpc'])
    expect(options.env.POLYMARKET_PROXY_WALLET).toBeUndefined()
    expect(options.env.CLOB_API_KEY).toBeUndefined()
    expect(child.stdin.end).toHaveBeenCalledWith(JSON.stringify(request))
    child.stdout.emit('data', Buffer.from('{"market_ids":["900001"]}'))
    child.emit('close', 0)
    expect(await result).toEqual({market_ids: ['900001']})
    delete process.env.POLYMARKET_PROXY_WALLET
    delete process.env.CLOB_API_KEY
  })
  it('rejects account or shell-shaped requests before spawning', () => {
    expect(() => runResearch({operation: 'ladder', args: ['cancel']})).toThrow()
    expect(mocks.spawn).not.toHaveBeenCalled()
  })
  it('watches only the research database and research exports', () => {
    const paths = researchWatchPaths()
    expect(paths.every(path => !/context|live|generated|sessions/.test(path))).toBe(true)
    expect(paths).toContain('/synthetic-repo/reports/research')
    const watcher = {on: vi.fn(), close: vi.fn().mockResolvedValue(undefined)}
    mocks.watch.mockReturnValue(watcher)
    const contents = {id: 40, once: vi.fn()} as unknown as WebContents
    startResearchWatch(contents)
    expect(mocks.watch).toHaveBeenCalledWith(paths, expect.any(Object))
    stopResearchWatch(40)
    expect(watcher.close).toHaveBeenCalled()
  })
})
