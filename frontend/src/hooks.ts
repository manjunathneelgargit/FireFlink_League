import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api'
import type { Demo, Meta, Revenue, Snapshot } from './types'

export const useSnapshot = () =>
  useQuery({ queryKey: ['dashboard'], queryFn: () => api.get<Snapshot>('/api/dashboard'), refetchInterval: 30_000 })

export const useMeta = () => useQuery({ queryKey: ['meta'], queryFn: () => api.get<Meta>('/api/meta'), staleTime: 60_000 })

export const useDemos = (deleted = false) =>
  useQuery({ queryKey: ['demos', deleted], queryFn: () => api.get<Demo[]>(`/api/demos${deleted ? '?deleted=true' : ''}`), refetchInterval: 60_000 })

export const useRevenue = (deleted = false) =>
  useQuery({ queryKey: ['revenue', deleted], queryFn: () => api.get<Revenue[]>(`/api/revenue${deleted ? '?deleted=true' : ''}`) })

/** After any mutation, refresh everything derived from league data. */
export function useRefreshAll() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'me' })
}
