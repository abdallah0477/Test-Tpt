import { useState, type FormEvent } from 'react'
import { validateUrl } from './validateUrl'

interface UrlBarProps {
  busy: boolean
  onStart: (url: string) => void
  /** Error from the backend (e.g. 422 invalid_url), shown under the field. */
  serverError?: string | null
}

export function UrlBar({ busy, onStart, serverError }: UrlBarProps) {
  const [value, setValue] = useState('')
  const [message, setMessage] = useState<string | null>(null)

  function submit(event: FormEvent) {
    event.preventDefault()
    const check = validateUrl(value)
    if (!check.ok) {
      setMessage(check.message) // nothing is sent to the backend
      return
    }
    setMessage(null)
    onStart(check.url)
  }

  const shown = message ?? serverError ?? null

  return (
    <form className="url-bar" onSubmit={submit} noValidate>
      <label htmlFor="target-url">Page URL</label>
      <input
        id="target-url"
        type="url"
        value={value}
        placeholder="https://example.com/login"
        onChange={(event) => setValue(event.target.value)}
        aria-invalid={shown !== null}
        aria-describedby={shown ? 'target-url-error' : undefined}
        autoComplete="url"
      />
      <button type="submit" className="btn btn-primary" disabled={busy}>
        {busy ? 'Inspecting…' : 'Start inspection'}
      </button>
      {shown && (
        <p id="target-url-error" className="field-error" role="alert">
          {shown}
        </p>
      )}
    </form>
  )
}
