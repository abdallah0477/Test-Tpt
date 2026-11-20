import { useQuery } from '@tanstack/react-query'
import { apiGet } from './client'
import type { Health } from './types'

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => apiGet<Health>('/health'),
    refetchInterval: 10_000,
  })
}
