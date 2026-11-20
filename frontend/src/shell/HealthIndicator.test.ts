import { describe, expect, it } from 'vitest'
import { modelStatusText } from './modelStatus'

const base = { reachable: true, model: 'qwen3:4b-instruct-2507-q4_K_M', warm: true, version: '0.40.16', error: null }

describe('modelStatusText', () => {
  it('ready / warming / not reachable', () => {
    expect(modelStatusText(base)).toEqual({ state: 'ok', text: 'Model ready (qwen3:4b-instruct-2507-q4_K_M, Ollama 0.40.16)' })
    expect(modelStatusText({ ...base, warm: false }).state).toBe('warn')
    expect(modelStatusText({ ...base, reachable: false, error: 'connection refused' })).toEqual({
      state: 'down',
      text: 'Model not reachable (qwen3:4b-instruct-2507-q4_K_M)',
    })
  })
})
