// Client-side URL check before anything is sent to the backend (Story 1.4).
// The backend validates again; this only gives a fast, friendly message.
export type UrlCheck = { ok: true; url: string } | { ok: false; message: string }

export function validateUrl(input: string): UrlCheck {
  const text = input.trim()
  if (text === '') return { ok: false, message: 'Enter a URL to inspect, for example https://example.com.' }
  let parsed: URL
  try {
    parsed = new URL(text)
  } catch {
    return { ok: false, message: 'This is not a valid URL. Include the scheme, for example https://example.com.' }
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return { ok: false, message: `Only http and https URLs can be inspected (got "${parsed.protocol}").` }
  }
  if (parsed.hostname === '') return { ok: false, message: 'The URL needs a host name.' }
  return { ok: true, url: text }
}
