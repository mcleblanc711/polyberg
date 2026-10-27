import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import type { ResearchList, ResearchRequest } from '../../../shared/research'
interface Context {
  data: ResearchList; loading: boolean; error: string
  query: {project?: string; all_markets?: boolean}
  setQuery: (value: {project?: string; all_markets?: boolean}) => void
  request: <T>(request: ResearchRequest) => Promise<T>
}
const ResearchContext = createContext<Context | null>(null)
export function ResearchProvider({ children }: {children: ReactNode}): JSX.Element {
  const [data, setData] = useState<ResearchList>({markets: [], projects: [], activity: {}, events: {}})
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState<{project?: string; all_markets?: boolean}>({})
  const current = useRef(0)
  const reload = useCallback(async () => {
    const generation = ++current.current
    try {
      const result = await window.research.request<ResearchList>({operation: 'list', ...query})
      if (generation === current.current) { setData(result); setError('') }
    } catch (e) { if (generation === current.current) setError(String(e)) }
  }, [query])
  useEffect(() => {
    void reload()
    let timer: ReturnType<typeof setTimeout>
    const unsubscribe = window.research.onChange(() => { clearTimeout(timer); timer = setTimeout(() => void reload(), 250) })
    return () => { current.current++; clearTimeout(timer); unsubscribe() }
  }, [reload])
  const request = async <T,>(input: ResearchRequest): Promise<T> => {
    setLoading(true); setError('')
    try { const result = await window.research.request<T>(input); await reload(); return result }
    catch (e) { setError(String(e)); throw e }
    finally { setLoading(false) }
  }
  return <ResearchContext.Provider value={{data, loading, error, query, setQuery, request}}>{children}</ResearchContext.Provider>
}
export function useResearch(): Context {
  const context = useContext(ResearchContext)
  if (!context) throw new Error('Research provider missing')
  return context
}
