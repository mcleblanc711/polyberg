import { existsSync, statSync } from 'fs'
import { dirname, isAbsolute, relative, resolve } from 'path'

const isRepoRoot = (dir: string): boolean =>
  existsSync(resolve(dir, 'pyproject.toml')) && existsSync(resolve(dir, 'context'))

const walkUpForRepo = (start: string): string | null => {
  let dir = start
  for (let i = 0; i < 10; i++) {
    if (isRepoRoot(dir)) return dir
    const parent = dirname(dir)
    if (parent === dir) return null
    dir = parent
  }
  return null
}

const findRepoRoot = (): string => {
  const override = process.env.POLYBERG_REPO
  if (override) {
    const abs = resolve(override)
    if (isRepoRoot(abs)) return abs
    throw new Error(
      `POLYBERG_REPO=${abs} does not look like a polyberg repo (missing pyproject.toml or context/)`
    )
  }
  const found = walkUpForRepo(__dirname)
  if (found) return found
  throw new Error(
    `Could not locate polyberg repo root from ${__dirname}. Set POLYBERG_REPO to the repo path.`
  )
}

export const REPO_ROOT = findRepoRoot()
export const CONTEXT_DIR = resolve(REPO_ROOT, 'context')
export const REPORTS_DIR = resolve(REPO_ROOT, 'reports', 'generated')
export const SNAPSHOTS_DIR = resolve(REPO_ROOT, 'data', 'snapshots')

const READ_ROOTS = [CONTEXT_DIR, REPORTS_DIR, SNAPSHOTS_DIR]
const WRITE_PATHS = new Set<string>([
  resolve(CONTEXT_DIR, 'recent_catalysts.md'),
  resolve(CONTEXT_DIR, 'open_orders.yaml')
])

const isInside = (root: string, p: string): boolean => {
  const rel = relative(root, p)
  return rel !== '' && !rel.startsWith('..') && !isAbsolute(rel)
}

export const assertReadable = (p: string): string => {
  const abs = resolve(p)
  if (!READ_ROOTS.some((root) => abs === root || isInside(root, abs))) {
    throw new Error(`Read denied (path outside allowed roots): ${abs}`)
  }
  return abs
}

export const assertWritable = (p: string): string => {
  const abs = resolve(p)
  if (!WRITE_PATHS.has(abs)) {
    throw new Error(`Write denied (path not in writable allowlist): ${abs}`)
  }
  return abs
}

export const ageMinutes = (p: string): number | null => {
  try {
    const m = statSync(p).mtimeMs
    return Math.round((Date.now() - m) / 60000)
  } catch {
    return null
  }
}
