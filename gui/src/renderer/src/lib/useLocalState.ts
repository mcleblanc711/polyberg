import { useEffect, useState, type Dispatch, type SetStateAction } from 'react'

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
      localStorage.setItem(key, JSON.stringify(value))
    } catch {
      // quota or serialization failure; persistence is best-effort
    }
  }, [key, value])

  return [value, setValue]
}
