// Small typed fetch wrapper. Every non-2xx response is parsed as the AD-14 error
// envelope {error: {code, message, details}} and thrown as ApiRequestError.
// Types come from src/api/types.ts (aliases into the generated schema.d.ts).
import type { components } from './schema'
import type { ErrorBody } from './types'

export type Schemas = components['schemas']
export type ApiError = ErrorBody

export const API_BASE = '/api/v1'

export class ApiRequestError extends Error {
  readonly status: number
  readonly error: ApiError

  constructor(status: number, error: ApiError) {
    super(error.message)
    this.name = 'ApiRequestError'
    this.status = status
    this.error = error
  }
}

/** Builds an absolute API URL, e.g. for <img src> or download links. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}

async function parseError(response: Response): Promise<ApiRequestError> {
  const body = (await response.json().catch(() => null)) as { error?: ApiError } | null
  const error = body?.error ?? {
    code: 'http_error',
    message: response.statusText || `HTTP ${response.status}`,
    details: null,
  }
  return new ApiRequestError(response.status, error)
}

async function request<T>(
  method: 'GET' | 'POST' | 'PUT',
  path: string,
  body?: unknown,
  extraHeaders: Record<string, string> = {},
): Promise<T> {
  const headers: Record<string, string> = { ...extraHeaders }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const response = await fetch(apiUrl(path), {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>('GET', path)
}

/** POST; pass `rev` for Session writes that need optimistic concurrency (If-Match). */
export function apiPost<T>(path: string, body?: unknown, rev?: number): Promise<T> {
  return request<T>('POST', path, body ?? {}, rev === undefined ? {} : { 'If-Match': String(rev) })
}

/**
 * PUT with optimistic concurrency (AD-14): `rev` is the Session.rev the change is based on.
 * A stale rev makes the backend answer 409 rev_conflict.
 */
export function apiPut<T>(path: string, body: unknown, rev: number): Promise<T> {
  return request<T>('PUT', path, body, { 'If-Match': String(rev) })
}

/** True for the 409 the backend sends when the stored rev moved on. */
export function isRevConflict(error: unknown): boolean {
  return error instanceof ApiRequestError && error.status === 409 && error.error.code === 'rev_conflict'
}

/** The AD-14 error code of an API error, or null for other errors. */
export function errorCode(error: unknown): string | null {
  return error instanceof ApiRequestError ? error.error.code : null
}

/** A readable one-line message for any error thrown by the hooks. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) return `${error.error.message} (${error.error.code})`
  if (error instanceof Error) return error.message
  return String(error)
}
