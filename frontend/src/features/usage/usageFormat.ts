// Text for the usage badge: "qwen3:4b · 2 calls · 1,250 tokens · 6.4 s" (Story 3.5).
import type { ResponseUsage } from '../../api/types'

/** "qwen3:4b-instruct-2507-q4_K_M" -> "qwen3:4b"; the full name stays in the details. */
export function shortModel(model: string): string {
  const [name, tag] = model.split(':')
  return tag ? `${name}:${tag.split('-')[0]}` : name
}

export function formatSeconds(ms: number | null | undefined): string {
  return ms == null ? '–' : `${(ms / 1000).toFixed(1)} s`
}

export function formatTokens(tokens: number | null | undefined): string {
  return tokens == null ? '–' : tokens.toLocaleString('en-US')
}

/** "1 call", "2 calls". */
export function plural(count: number, word: string): string {
  return `${count.toLocaleString('en-US')} ${count === 1 ? word : `${word}s`}`
}

export function badgeText(usage: ResponseUsage): string {
  const calls = plural(usage.calls, 'call')
  const reused = usage.reused_calls > 0 ? ` (+${usage.reused_calls} reused)` : ''
  return `${shortModel(usage.model)} · ${calls}${reused} · ${formatTokens(usage.total_tokens)} tokens · ${formatSeconds(usage.response_ms)}`
}
