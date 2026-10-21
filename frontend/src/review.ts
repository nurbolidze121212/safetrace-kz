import type { Case } from './types'

export type ReviewRecency = 'none' | 'updating' | 'earlier' | 'unknown' | 'saved'

export function reviewRecency(current: Pick<Case, 'status' | 'analyzed_at' | 'decisions'>): ReviewRecency {
  if (current.status === 'pending' || current.status === 'running') return 'updating'
  const last = current.decisions.at(-1)
  if (!last) return 'none'
  const analysisTime = Date.parse(current.analyzed_at || '')
  const decisionTime = Date.parse(last.at)
  if (!Number.isFinite(analysisTime) || !Number.isFinite(decisionTime)) return 'unknown'
  return analysisTime > decisionTime ? 'earlier' : 'saved'
}
