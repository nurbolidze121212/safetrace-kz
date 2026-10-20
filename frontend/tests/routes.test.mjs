import test from 'node:test'
import assert from 'node:assert/strict'
import { routePaths } from '../src/routes.ts'

const relation = (from, to, observation_id, type = 'redirects') => ({ from, to, observation_id, type, evidence_id: observation_id + '-e' })
const observation = (id, url, extra = {}) => ({ id, url, status_code: 200, text: '', ...extra })

test('two publications converging on one destination remain two ordered paths', () => {
  const trace = {
    observations: [observation('1', 'https://a.test/one'), observation('2', 'https://a.test/two'), observation('3', 'https://b.test/hub'), observation('4', 'https://c.test/?ref=X'), observation('5', 'https://c.test/?ref=X', { reused_from: '4' })],
    relations: [relation(null, 'https://a.test/one', '1', 'contains_link'), relation(null, 'https://a.test/two', '2', 'contains_link'), relation('https://a.test/one', 'https://b.test/hub', '3'), relation('https://a.test/two', 'https://c.test/?ref=X', '4'), relation('https://b.test/hub', 'https://c.test/?ref=X', '5', 'page_link')],
  }
  const paths = routePaths(trace)
  assert.deepEqual(paths.map(p => p.steps.map(s => s.observation.id)), [['1', '3', '5'], ['2', '4']])
  assert.equal(paths[0].steps[2].relation.type, 'page_link')
  assert.equal(paths[0].steps[2].observation.reused_from, '4')
})

test('cycle is a visible terminal step, not an infinite route', () => {
  const trace = { observations: [observation('1', 'A'), observation('2', 'B'), observation('3', 'A')], relations: [relation(null, 'A', '1'), relation('A', 'B', '2'), relation('B', 'A', '3')] }
  const paths = routePaths(trace)
  assert.equal(paths.length, 1)
  assert.equal(paths[0].steps.length, 3)
  assert.equal(paths[0].steps[2].cycle, true)
})

test('stopped observation does not imply that a later unrelated edge was checked', () => {
  const trace = { observations: [observation('1', 'A', { stop: 'Blocked destination', status_code: null }), observation('2', 'B')], relations: [relation(null, 'A', '1'), relation('A', 'B', '2')] }
  assert.deepEqual(routePaths(trace)[0].steps.map(s => s.observation.id), ['1'])
})

test('different destination query values retain separate branch identities', () => {
  const trace = { observations: [observation('1', 'root'), observation('2', 'target?ref=A'), observation('3', 'target?ref=B')], relations: [relation(null, 'root', '1'), relation('root', 'target?ref=A', '2'), relation('root', 'target?ref=B', '3')] }
  assert.deepEqual(routePaths(trace).map(p => p.steps.at(-1).relation.to), ['target?ref=A', 'target?ref=B'])
})
