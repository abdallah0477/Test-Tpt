import type { ModelStatus } from '../api/types'

export type State = 'ok' | 'checking' | 'warn' | 'down'

export const DOT: Record<State, string> = { ok: '●', checking: '○', warn: '◐', down: '✕' }

/** Model status as text: reachable / warming up / not reachable (never colour alone). */
export function modelStatusText(model: ModelStatus): { state: State; text: string } {
  const name = model.model || 'model'
  if (!model.reachable) return { state: 'down', text: `Model not reachable (${name})` }
  if (!model.warm) return { state: 'warn', text: `Model warming up (${name})` }
  return { state: 'ok', text: `Model ready (${name}${model.version ? `, Ollama ${model.version}` : ''})` }
}
