import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'
import {
  IPC,
  type Catalyst,
  type ContextChangeEvent,
  type DraftOrder,
  type PasteKind,
  type PmBridge,
  type RunStageResult
} from '../shared/contract'

let streamSeq = 0

const pm: PmBridge = {
  readContext: () => ipcRenderer.invoke(IPC.readContext),

  readArtifact: (name) => ipcRenderer.invoke(IPC.readArtifact, name),

  writeClipboard: (text) => ipcRenderer.invoke(IPC.writeClipboard, text),

  runStage: (name, args) => ipcRenderer.invoke(IPC.runStage, name, args),

  runStageStream: (name, args, onChunk) => {
    const requestId = `s${++streamSeq}`
    const handler = (
      _evt: IpcRendererEvent,
      payload: { requestId: string; stream: 'stdout' | 'stderr'; text: string }
    ): void => {
      if (payload.requestId !== requestId) return
      onChunk({ stream: payload.stream, text: payload.text })
    }
    ipcRenderer.on(IPC.runStageStreamChunk, handler)
    return (ipcRenderer.invoke(IPC.runStageStream, requestId, name, args) as Promise<RunStageResult>)
      .finally(() => ipcRenderer.off(IPC.runStageStreamChunk, handler))
  },

  appendCatalyst: (marketId: string, entry: Catalyst) =>
    ipcRenderer.invoke(IPC.appendCatalyst, marketId, entry),

  writeDraftOrder: (order: DraftOrder) => ipcRenderer.invoke(IPC.writeDraftOrder, order),

  writePasteInput: (kind: PasteKind, text: string) =>
    ipcRenderer.invoke(IPC.writePasteInput, kind, text),

  onContextChange: (cb) => {
    const handler = (_evt: IpcRendererEvent, payload: ContextChangeEvent): void => cb(payload)
    ipcRenderer.on(IPC.watchEvent, handler)
    void ipcRenderer.invoke(IPC.watchStart)
    return () => {
      ipcRenderer.off(IPC.watchEvent, handler)
      void ipcRenderer.invoke(IPC.watchStop)
    }
  }
}

contextBridge.exposeInMainWorld('pm', pm)
