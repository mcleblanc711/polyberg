import type { PmBridge } from '../shared/contract'

declare global {
  interface Window {
    pm: PmBridge
  }
}

export {}
