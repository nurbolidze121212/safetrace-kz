import type { Case, Observation, Relation, Trace } from './types'

export type RouteStep = { relation: Relation; observation?: Observation; cycle?: boolean }
export type RoutePath = { root: string; steps: RouteStep[] }

// Attribute a displayed route only through the recorded material -> URL edge.
export function routeMaterialIds(current: Pick<Case, 'graph'>, root: string): Set<string> {
  const nodes = new Map(current.graph.nodes.map(node => [node.id, node]))
  return new Set(current.graph.edges.filter(edge => edge.type === 'contains_link' && nodes.get(edge.target)?.label === root)
    .map(edge => nodes.get(edge.source)?.material_id).filter((id): id is string => Boolean(id)))
}

// Follow recorded edges, never infer a redirect from chronological adjacency.
export function routePaths(trace: Trace): RoutePath[] {
  const relations = trace.relations || []
  const observations = new Map(trace.observations.map(o => [o.id, o]))
  const paths: RoutePath[] = []
  function walk(root: string, relation: Relation, steps: RouteStep[], visited: Set<string>) {
    const cycle = visited.has(relation.to)
    const step = { relation, observation: observations.get(relation.observation_id), cycle }
    const next = [...steps, step]
    const outgoing = relations.filter(r => r.from === relation.to)
    if (cycle || step.observation?.stop || !outgoing.length || next.length >= 16) {
      paths.push({ root, steps: next })
      return
    }
    const seen = new Set([...visited, relation.to])
    for (const child of outgoing) walk(root, child, next, seen)
  }
  for (const root of relations.filter(r => !r.from)) walk(root.to, root, [], new Set())
  return paths
}
