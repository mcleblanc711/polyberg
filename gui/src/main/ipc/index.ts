import { ipcMain, type IpcMainInvokeEvent } from 'electron'
import { IPC, type Catalyst, type DraftOrder, type PasteKind } from '../../shared/contract'
import { readContext } from './readContext'
import { runStage, runStageStream } from './runStage'
import { appendCatalyst, writeDraftOrder, writePasteInput } from './writers'
import { startWatch, stopWatch } from './watcher'

let registered = false

export const registerIpc = (): void => {
  if (registered) return
  registered = true

  ipcMain.handle(IPC.readContext, () => readContext())

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

  ipcMain.handle(IPC.watchStart, (evt: IpcMainInvokeEvent) => {
    startWatch(evt.sender)
  })

  ipcMain.handle(IPC.watchStop, (evt: IpcMainInvokeEvent) => {
    stopWatch(evt.sender.id)
  })
}
