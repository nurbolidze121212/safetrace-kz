import test from 'node:test'
import assert from 'node:assert/strict'
import { routeMaterialIds } from '../src/routes.ts'

test('presentation routes stay attached to their own input rather than a shared destination or referral', () => {
  const current = { graph: {
    nodes: [
      { id: 'm1', material_id: 'first', type: 'material' }, { id: 'm2', material_id: 'second', type: 'material' },
      { id: 'u1', label: 'https://one.test/?ref=42' }, { id: 'u2', label: 'https://two.test/?ref=42' },
      { id: 'end', label: 'https://destination.test/' },
    ],
    edges: [
      { source: 'm1', target: 'u1', type: 'contains_link' }, { source: 'm2', target: 'u2', type: 'contains_link' },
      { source: 'u1', target: 'end', type: 'redirects' }, { source: 'u2', target: 'end', type: 'page_link' },
      { source: 'm1', target: 'm2', type: 'matching_identifier' },
    ],
  } }
  assert.deepEqual([...routeMaterialIds(current, 'https://one.test/?ref=42')], ['first'])
  assert.deepEqual([...routeMaterialIds(current, 'https://two.test/?ref=42')], ['second'])
  assert.equal(routeMaterialIds(current, 'https://destination.test/').size, 0)
})

test('a route shared by two actual source edges keeps both sources; missing evidence does not invent one', () => {
  const current = { graph: { nodes: [{ id: 'a', material_id: 'first' }, { id: 'b', material_id: 'second' }, { id: 'url', label: 'https://same.test/' }], edges: [{ source: 'a', target: 'url', type: 'contains_link' }, { source: 'b', target: 'url', type: 'contains_link' }, { source: 'missing', target: 'url', type: 'contains_link' }] } }
  assert.deepEqual([...routeMaterialIds(current, 'https://same.test/')], ['first', 'second'])
  assert.equal(routeMaterialIds(current, 'https://unseen.test/').size, 0)
})
