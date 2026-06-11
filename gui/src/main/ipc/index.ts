import { clipboard, ipcMain, type IpcMainInvokeEvent } from 'electron'
import {
  IPC,
  type ArtifactName,
  type Catalyst,
  type DraftOrder,
  type PasteKind,
  type ResponseSlot,
  type SchemaName
} from '../../shared/contract'
import { readArtifact } from './readArtifact'
import { readContext } from './readContext'
import { readSchema } from './readSchema'
import { runStage, runStageStream } from './runStage'
import { appendCatalyst, writeDraftOrder, writePasteInput, writeResponseInput } from './writers'
import { startWatch, stopWatch } from './watcher'

let registered = false

export const registerIpc = (): void => {
  if (registered) return
  registered = true

  ipcMain.handle(IPC.readContext, () => readContext())

  ipcMain.handle(IPC.readArtifact, (_evt, name: ArtifactName) => readArtifact(name))

  ipcMain.handle(IPC.readSchema, (_evt, name: SchemaName) => readSchema(name))

  ipcMain.handle(IPC.writeClipboard, (_evt, text: string) => {
    if (typeof text !== 'string') {
      throw new Error('writeClipboard expects a string')
    }
    clipboard.writeText(text)
  })

  ipcMain.handle(IPC.runStage, (_evt, name: string, args?: string[]) => runStage(name, args))

  ipcMain.handle(
    IPC.runStageStream,
    (evt: IpcMainInvokeEvent, requestId: string, name: string, args?: string[]) =>
      runStageStream(evt.sender, requestId, name, Array.isArray(args) ? args : [])
  )

  ipcMain.handle(IPC.appendCatalyst, (_evt, marketId: string, entry: Catalyst) => {
    appendCatalyst(marketId, entry)
  })

  ipcMain.handle(IPC.writeDraftOrder, (_evt, order: DraftOrder) => {
    writeDraftOrder(order)
  })

  ipcMain.handle(IPC.writePasteInput, (_evt, kind: PasteKind, text: string) => {
    return writePasteInput(kind, text)
  })

  ipcMain.handle(IPC.writeResponseInput, (_evt, slot: ResponseSlot, text: string) => {
    return writeResponseInput(slot, text)
  })

  ipcMain.handle(IPC.watchStart, (evt: IpcMainInvokeEvent) => {
    startWatch(evt.sender)
  })

  ipcMain.handle(IPC.watchStop, (evt: IpcMainInvokeEvent) => {
    stopWatch(evt.sender.id)
  })
}
