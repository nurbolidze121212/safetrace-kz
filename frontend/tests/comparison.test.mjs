import { test } from 'node:test'
import assert from 'node:assert/strict'
import { compareObservations } from '../src/comparison.ts'

const observation = (url, text = 'Сохраненный текст') => ({ id: 'old', url, at: '2026-10-20', status_code: 200, text, evidence_id: 'e1', method: 'synthetic_transport' })
test('new IDs and timestamps do not claim page changes; actual body changes do', () => {
  const old = { observations: [observation('https://a.test/x')] }
  const now = { observations: [{ ...observation('https://a.test/x'), id: 'new', at: '2026-10-21', evidence_id: 'e2' }] }
  assert.equal(compareObservations(old, now)[0].kind, 'same')
  now.observations[0].text = 'Другое назначение'
  assert.deepEqual(compareObservations(old, now)[0].changes, ['Текст страницы'])
})
test('different referral queries remain separate; absent is not a claim of deletion', () => {
  const rows = compareObservations({ observations: [observation('https://a.test/?ref=A')] }, { observations: [observation('https://a.test/?ref=B')] })
  assert.deepEqual(rows.map(r => r.kind), ['added', 'absent'])
})
test('HTML links and redirects are compared separately even with the same endpoint', () => {
  const relation = { from: 'https://a.test/', to: 'https://b.test/', type: 'redirects', quote: 'go' }
  const before = { observations: [observation('https://a.test/')], relations: [relation] }
  const after = { observations: before.observations, relations: [{ ...relation, type: 'page_link' }] }
  assert.deepEqual(compareObservations(before, after)[0].changes, ['Переходы'])
})
