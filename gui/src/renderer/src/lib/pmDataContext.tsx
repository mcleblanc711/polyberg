import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode
} from 'react'
import { fmtCents, fmtPct, fmtUsd } from './format'
import { makeMarketById, makeSuggestMarket } from './pmData'
import type { PmData, PmDataPayload } from './types'

const PmDataContext = createContext<PmData | null>(null)
const PmDataRefreshContext = createContext<() => Promise<void>>(async () => undefined)

const buildPmData = (payload: PmDataPayload): PmData => ({
  ...payload,
  fmtUsd,
  fmtPct,
  fmtCents,
  suggestMarket: makeSuggestMarket(payload.markets),
  marketById: makeMarketById(payload.markets)
})

export const PmDataProvider = ({ children }: { children: ReactNode }) => {
  const [pmData, setPmData] = useState<PmData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inflight = useRef(false)

  const refresh = async (): Promise<void> => {
    if (inflight.current) return
    inflight.current = true
    try {
      const payload = await window.pm.readContext()
      setPmData(buildPmData(payload))
      setError(null)
    } catch (e) {
      setError(String(e))
    } finally {
      inflight.current = false
    }
  }

  useEffect(() => {
    void refresh()
    const unsubscribe = window.pm.onContextChange(() => {
      void refresh()
    })
    return () => unsubscribe()
  }, [])

  if (error) return <BootError msg={error} />
  if (!pmData) return <BootSplash />
  return (
    <PmDataContext.Provider value={pmData}>
      <PmDataRefreshContext.Provider value={refresh}>{children}</PmDataRefreshContext.Provider>
    </PmDataContext.Provider>
  )
}

export const usePmData = (): PmData => {
  const v = useContext(PmDataContext)
  if (!v) throw new Error('usePmData called outside PmDataProvider')
  return v
}

export const usePmDataRefresh = (): (() => Promise<void>) => useContext(PmDataRefreshContext)

const splashStyle = {
  width: '100vw',
  height: '100vh',
  background: '#050007',
  color: '#7a4f86',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontFamily: 'monospace',
  fontSize: 12,
  letterSpacing: 0.6
} as const

const BootSplash = () => <div style={splashStyle}>polyberg / loading context…</div>

const BootError = ({ msg }: { msg: string }) => (
  <div style={{ ...splashStyle, color: '#ff3d6b', padding: 24, whiteSpace: 'pre-wrap' }}>
    polyberg / context load failed{'\n\n'}
    {msg}
  </div>
)
