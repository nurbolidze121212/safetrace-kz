import test from 'node:test'
import assert from 'node:assert/strict'
import { graphScopeEdges } from '../src/graphScope.ts'

const graph = {
  nodes: [
    { id: 'a', case_id: 'current' }, { id: 'b', case_id: 'current' },
    { id: 'peer', case_id: 'other' }, { id: 'url' }, { id: 'identifier' },
  ],
  edges: [
    { id: 'input', source: 'a', target: 'url', type: 'contains_link' },
    { id: 'code', source: 'url', target: 'identifier', type: 'contains_identifier' },
    { id: 'local-match', source: 'a', target: 'b', type: 'matching_identifier', evidence_ids: ['original-a', 'original-b', 'observed-destination'] },
    { id: 'outbound-peer', source: 'a', target: 'peer', type: 'matching_identifier' },
    { id: 'inbound-peer', source: 'peer', target: 'b', type: 'matching_identifier' },
  ],
}

test('case scope keeps the relationship and sources between its own materials while excluding peer endpoints', () => {
  const result = graphScopeEdges(graph, 'current', 'case')
  assert.deepEqual(result.map(edge => edge.id), ['input', 'code', 'local-match'])
  assert.deepEqual(result[2].evidence_ids, ['original-a', 'original-b', 'observed-destination'])
  assert.equal(result[2], graph.edges[2])
  assert.equal(graph.edges.length, 5)
})

test('route and all scopes retain their distinct meanings and do not depend on a prior filter', () => {
  assert.deepEqual(graphScopeEdges(graph, 'current', 'route').map(edge => edge.id), ['input', 'code'])
  assert.equal(graphScopeEdges(graph, 'current', 'all'), graph.edges)
  assert.deepEqual(graphScopeEdges({ nodes: [], edges: [] }, 'current', 'case'), [])
})
