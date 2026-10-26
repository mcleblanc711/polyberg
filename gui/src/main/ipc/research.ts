import { spawn } from 'child_process'
import { existsSync } from 'fs'
import { resolve } from 'path'
import chokidar, { type FSWatcher } from 'chokidar'
import type { WebContents } from 'electron'
import { RESEARCH_IPC, validateResearchRequest } from '../../shared/research'
import { REPO_ROOT } from './repo'

export const RESEARCH_DB = resolve(process.env.POLYBERG_RESEARCH_DB || resolve(REPO_ROOT, 'data/research/research.sqlite3'))
export const RESEARCH_EXPORTS = resolve(REPO_ROOT, 'reports/research')
export const researchWatchPaths = (): string[] => [RESEARCH_DB, `${RESEARCH_DB}-wal`, `${RESEARCH_DB}-journal`, RESEARCH_EXPORTS]

export const runResearch = (input: unknown): Promise<unknown> => {
  const request = validateResearchRequest(input)
  const venv = resolve(REPO_ROOT, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
  const python = existsSync(venv) ? venv : process.platform === 'win32' ? 'python' : 'python3'
  return new Promise((resolveP, reject) => {
    const child = spawn(python, ['-m', 'polyberg.cli', '--db', RESEARCH_DB, 'research', 'rpc'], {
      cwd: REPO_ROOT,
      // Do not pass wallet credentials to the public process.
      env: Object.fromEntries(Object.entries(process.env).filter(([key]) =>
        !/^(POLYMARKET_|CLOB_|POLY_(ADDRESS|SIGNATURE|API|SECRET|PASSPHRASE))/.test(key)))
    })
    let stdout = ''
    const timer = setTimeout(() => { child.kill(); reject(new Error('Public research request timed out')) }, 300000)
    child.stdout.on('data', (data: Buffer) => {
      stdout += data.toString('utf8')
      if (stdout.length > 20000000) { child.kill(); reject(new Error('Research result too large')) }
    })
    // Never reflect subprocess stderr or arbitrary upstream payloads into the renderer.
    child.stderr.resume()
    child.stdin.on('error', () => undefined)
    child.on('error', () => { clearTimeout(timer); reject(new Error('Could not start research Python process')) })
    child.on('close', (code) => {
      clearTimeout(timer)
      try {
        const result = JSON.parse(stdout)
        if (code !== 0 || result.error) reject(new Error(result.error || 'Research operation failed'))
        else resolveP(result)
      } catch { reject(new Error('Invalid research subprocess response')) }
    })
    child.stdin.end(JSON.stringify(request))
  })
}

const watchers = new Map<number, FSWatcher>()
export const startResearchWatch = (contents: WebContents): void => {
  if (watchers.has(contents.id)) return
  const watcher = chokidar.watch(researchWatchPaths(), { ignoreInitial: true, awaitWriteFinish: { stabilityThreshold: 150, pollInterval: 50 } })
  watchers.set(contents.id, watcher)
  watcher.on('all', (_event, path) => {
    // SQLite rollback journals are removed after commit; other events cover DB and published exports.
    if (!contents.isDestroyed() && !path.includes('.research-export-')) contents.send(RESEARCH_IPC.changed)
  })
  contents.once('destroyed', () => stopResearchWatch(contents.id))
}
export const stopResearchWatch = (id: number): void => {
  void watchers.get(id)?.close()
  watchers.delete(id)
}
