// The current session id is kept in localStorage only as a convenience across reloads.
// Storage can be unavailable (private mode, blocked site data), so every access is guarded.
import { useCallback, useState } from 'react'

const KEY = 'wta.session_id'

function read(): string | null {
  try {
    return window.localStorage.getItem(KEY)
  } catch {
    return null
  }
}

function write(value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(KEY)
    else window.localStorage.setItem(KEY, value)
  } catch {
    // ignore: the app still works for this page load
  }
}

export function useStoredSessionId(): [string | null, (value: string | null) => void] {
  const [sessionId, setSessionId] = useState<string | null>(read)
  const set = useCallback((value: string | null) => {
    write(value)
    setSessionId(value)
  }, [])
  return [sessionId, set]
}
