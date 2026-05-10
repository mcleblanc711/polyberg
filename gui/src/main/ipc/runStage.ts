import { spawn } from 'child_process'
import { existsSync } from 'fs'
import { resolve } from 'path'
import type { WebContents } from 'electron'
import { isAllowedStage, IPC, type RunStageResult } from '../../shared/contract'
import { REPO_ROOT } from './repo'

const pickPython = (): string => {
  const venv = resolve(REPO_ROOT, '.venv', 'bin', 'python')
  return existsSync(venv) ? venv : 'python3'
}

const sanitizeArgs = (args: string[] | undefined): string[] => {
  if (!Array.isArray(args)) return []
  return args.filter((a): a is string => typeof a === 'string')
}

const runOnce = (
  name: string,
  args: string[],
  onChunk?: (chunk: { stream: 'stdout' | 'stderr'; text: string }) => void
): Promise<RunStageResult> =>
  new Promise((resolveP) => {
    if (!isAllowedStage(name)) {
      resolveP({
        ok: false,
        code: -1,
        stdout: '',
        stderr: `Stage "${name}" is not in the allowlist`
      })
      return
    }
    const py = pickPython()
    const child = spawn(py, ['-m', 'polyberg.cli', name, ...sanitizeArgs(args)], {
      cwd: REPO_ROOT,
      env: process.env
    })
    let stdout = ''
    let stderr = ''
    child.stdout.on('data', (buf: Buffer) => {
      const text = buf.toString('utf8')
      stdout += text
      onChunk?.({ stream: 'stdout', text })
    })
    child.stderr.on('data', (buf: Buffer) => {
      const text = buf.toString('utf8')
      stderr += text
      onChunk?.({ stream: 'stderr', text })
    })
    child.on('error', (err) => {
      resolveP({ ok: false, code: -1, stdout, stderr: stderr + String(err) })
    })
    child.on('close', (code) => {
      resolveP({ ok: code === 0, code: code ?? -1, stdout, stderr })
    })
  })

export const runStage = (name: string, args?: string[]): Promise<RunStageResult> =>
  runOnce(name, sanitizeArgs(args))

export const runStageStream = (
  webContents: WebContents,
  requestId: string,
  name: string,
  args: string[]
): Promise<RunStageResult> =>
  runOnce(name, sanitizeArgs(args), (chunk) => {
    if (webContents.isDestroyed()) return
    webContents.send(IPC.runStageStreamChunk, { requestId, ...chunk })
  })
