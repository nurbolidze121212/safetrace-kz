import type { GraphData } from './types'

export type GraphScope = 'route' | 'case' | 'all'
const routeTypes = new Set(['contains_link', 'redirects', 'page_link', 'contains_identifier'])

export function graphScopeEdges(data: GraphData, caseId: string, scope: GraphScope) {
  if (scope === 'all') return data.edges
  if (scope === 'route') return data.edges.filter(edge => routeTypes.has(edge.type))
  const peers = new Set(data.nodes.filter(node => node.case_id && node.case_id !== caseId).map(node => node.id))
  return data.edges.filter(edge => !peers.has(edge.source) && !peers.has(edge.target))
}
