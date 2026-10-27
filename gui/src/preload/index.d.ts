import type { PmBridge } from '../shared/contract'

import type { ResearchBridge } from '../shared/research'

declare global {
  interface Window {
    pm: PmBridge
    research: ResearchBridge
  }
}

export {}
