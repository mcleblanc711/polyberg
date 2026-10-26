import { clipboard, ipcMain, shell, type IpcMainInvokeEvent } from 'electron'
import { IPC, type ArtifactName, type Catalyst, type DraftOrder, type PasteKind, type ResponseSlot, type SchemaName } from '../../shared/contract'
import { RESEARCH_IPC } from '../../shared/research'
import { runResearch, startResearchWatch, stopResearchWatch } from './research'
import { clearWorkspace, requireLegacy, selectWorkspace } from './workspaceAccess'

let registered = false
export const registerIpc = (): void => {
  if (registered) return
  registered = true
  ipcMain.handle(RESEARCH_IPC.request, (_evt, request: unknown) => runResearch(request))
  ipcMain.handle(RESEARCH_IPC.watchStart, async (evt) => {
    selectWorkspace(evt.sender.id, 'research')
    const { stopWatch } = await import('./watcher')
    stopWatch(evt.sender.id)
    startResearchWatch(evt.sender)
  })
  ipcMain.handle(RESEARCH_IPC.watchStop, (evt) => stopResearchWatch(evt.sender.id))
  ipcMain.handle(RESEARCH_IPC.workspace, async (evt, workspace: unknown) => {
    selectWorkspace(evt.sender.id, workspace)
    if (workspace === 'research') {
      const { stopWatch } = await import('./watcher')
      stopWatch(evt.sender.id)
    } else stopResearchWatch(evt.sender.id)
    evt.sender.once('destroyed', () => clearWorkspace(evt.sender.id))
  })
  ipcMain.handle(IPC.readContext, async (evt) => {
    requireLegacy(evt.sender.id)
    return (await import('./readContext')).readContext()
  })
  ipcMain.handle(IPC.readArtifact, async (evt, name: ArtifactName) => {
    requireLegacy(evt.sender.id)
    return (await import('./readArtifact')).readArtifact(name)
  })
  ipcMain.handle(IPC.readSchema, async (evt, name: SchemaName) => {
    requireLegacy(evt.sender.id)
    return (await import('./readSchema')).readSchema(name)
  })
  ipcMain.handle(IPC.writeClipboard, (_evt, text: string) => {
    if (typeof text !== 'string') throw new Error('writeClipboard expects a string')
    clipboard.writeText(text)
  })
  ipcMain.handle(IPC.openExternal, (_evt, url: string) => {
    if (typeof url !== 'string' || !/^https?:\/\//.test(url)) throw new Error('openExternal expects an http(s) URL')
    return shell.openExternal(url)
  })
  ipcMain.handle(IPC.runStage, async (evt, name: string, args?: string[]) => {
    requireLegacy(evt.sender.id)
    return (await import('./runStage')).runStage(name, args)
  })
  ipcMain.handle(IPC.runStageStream, async (evt: IpcMainInvokeEvent, requestId: string, name: string, args?: string[]) => {
    requireLegacy(evt.sender.id)
    return (await import('./runStage')).runStageStream(evt.sender, requestId, name, Array.isArray(args) ? args : [])
  })
  ipcMain.handle(IPC.appendCatalyst, async (evt, marketId: string, entry: Catalyst) => {
    requireLegacy(evt.sender.id)
    return (await import('./writers')).appendCatalyst(marketId, entry)
  })
  ipcMain.handle(IPC.writeDraftOrder, async (evt, order: DraftOrder) => {
    requireLegacy(evt.sender.id)
    return (await import('./writers')).writeDraftOrder(order)
  })
  ipcMain.handle(IPC.writePasteInput, async (evt, kind: PasteKind, text: string) => {
    requireLegacy(evt.sender.id)
    return (await import('./writers')).writePasteInput(kind, text)
  })
  ipcMain.handle(IPC.writeResponseInput, async (evt, slot: ResponseSlot, text: string) => {
    requireLegacy(evt.sender.id)
    return (await import('./writers')).writeResponseInput(slot, text)
  })
  ipcMain.handle(IPC.watchStart, async (evt: IpcMainInvokeEvent) => {
    requireLegacy(evt.sender.id)
    return (await import('./watcher')).startWatch(evt.sender)
  })
  ipcMain.handle(IPC.watchStop, async (evt: IpcMainInvokeEvent) => (await import('./watcher')).stopWatch(evt.sender.id))
}
