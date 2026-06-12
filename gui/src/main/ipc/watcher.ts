import chokidar, { type FSWatcher } from 'chokidar'
import { relative } from 'path'
import type { WebContents } from 'electron'
import { CONTEXT_DIR, LIVE_DIR, REPO_ROOT, REPORTS_DIR, SNAPSHOTS_DIR } from './repo'
import { IPC, type ContextChangeEvent } from '../../shared/contract'

const DEBOUNCE_MS = 300

interface Subscription {
  watcher: FSWatcher
  timer: NodeJS.Timeout | null
  pending: ContextChangeEvent[]
}

const subs = new Map<number, Subscription>()

const flush = (webContents: WebContents, sub: Subscription): void => {
  sub.timer = null
  if (webContents.isDestroyed()) return
  const events = sub.pending
  sub.pending = []
  for (const ev of events) webContents.send(IPC.watchEvent, ev)
}

export const startWatch = (webContents: WebContents): void => {
  const id = webContents.id
  if (subs.has(id)) return

  const watcher = chokidar.watch([CONTEXT_DIR, REPORTS_DIR, SNAPSHOTS_DIR, LIVE_DIR], {
    ignoreInitial: true,
    awaitWriteFinish: { stabilityThreshold: 100, pollInterval: 50 }
  })

  const sub: Subscription = { watcher, timer: null, pending: [] }
  subs.set(id, sub)

  const queue = (kind: ContextChangeEvent['kind']) => (path: string) => {
    sub.pending.push({ path: relative(REPO_ROOT, path), kind })
    if (sub.timer === null) {
      sub.timer = setTimeout(() => flush(webContents, sub), DEBOUNCE_MS)
    }
  }

  watcher.on('add', queue('add'))
  watcher.on('change', queue('change'))
  watcher.on('unlink', queue('unlink'))

  webContents.on('destroyed', () => stopWatch(id))
}

export const stopWatch = (webContentsId: number): void => {
  const sub = subs.get(webContentsId)
  if (!sub) return
  if (sub.timer !== null) clearTimeout(sub.timer)
  void sub.watcher.close()
  subs.delete(webContentsId)
}
