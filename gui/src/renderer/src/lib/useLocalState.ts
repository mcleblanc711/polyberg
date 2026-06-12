import { useEffect, useState, type Dispatch, type SetStateAction } from 'react'

// Same-window sync channel: two components holding the same key (e.g. the
// intake queue in IntakeScreen and its badge in the TopBar) stay in step.
const SYNC_EVENT = 'polyberg:localstate'

export const useLocalState = <T>(
  key: string,
  fallback: T
): [T, Dispatch<SetStateAction<T>>] => {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key)
      return raw === null ? fallback : (JSON.parse(raw) as T)
    } catch {
      return fallback
    }
  })

  useEffect(() => {
    try {
      const serialized = JSON.stringify(value)
      // Skipping the no-op write also breaks the dispatch→re-read→dispatch loop
      // between hook instances sharing a key.
      if (localStorage.getItem(key) !== serialized) {
        localStorage.setItem(key, serialized)
        window.dispatchEvent(new CustomEvent(SYNC_EVENT, { detail: key }))
      }
    } catch {
      // quota or serialization failure; persistence is best-effort
    }
  }, [key, value])

  useEffect(() => {
    const onSync = (e: Event): void => {
      if ((e as CustomEvent<string>).detail !== key) return
      try {
        const raw = localStorage.getItem(key)
        if (raw === null) return
        setValue((prev) => {
          try {
            if (JSON.stringify(prev) === raw) return prev
          } catch {
            // fall through to re-parse
          }
          return JSON.parse(raw) as T
        })
      } catch {
        // ignore malformed storage
      }
    }
    window.addEventListener(SYNC_EVENT, onSync)
    return () => window.removeEventListener(SYNC_EVENT, onSync)
  }, [key])

  return [value, setValue]
}
