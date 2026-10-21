import test from 'node:test'
import assert from 'node:assert/strict'
import { reviewRecency } from '../src/review.ts'

const decision = { id: 1, at: '2026-10-21T04:52:00+05:00', decision: 'confirmed', comment: 'Checked sources' }
const current = { status: 'completed', analyzed_at: '2026-10-20T23:50:00Z', decisions: [decision] }

test('a new analysis makes the earlier decision visibly historical, without changing it', () => {
  assert.equal(reviewRecency(current), 'saved')
  assert.equal(reviewRecency({ ...current, analyzed_at: '2026-10-20T23:54:00Z' }), 'earlier')
  assert.equal(reviewRecency({ ...current, analyzed_at: '2026-10-20T23:54:00Z', decisions: [decision, { ...decision, id: 2, at: '2026-10-20T23:55:00Z' }] }), 'saved')
  assert.equal(current.decisions.length, 1)
})

test('pending and running work cannot present a saved decision as applying to its result', () => {
  for (const status of ['pending', 'running']) {
    assert.equal(reviewRecency({ ...current, status }), 'updating')
    assert.equal(reviewRecency({ ...current, status, decisions: [] }), 'updating')
  }
  assert.equal(reviewRecency({ ...current, status: 'partial', analyzed_at: '2026-10-20T23:54:00Z' }), 'earlier')
})

test('legacy or malformed dates do not claim a verified time relationship', () => {
  assert.equal(reviewRecency({ ...current, analyzed_at: undefined }), 'unknown')
  assert.equal(reviewRecency({ ...current, decisions: [{ ...decision, at: 'invalid' }] }), 'unknown')
  assert.equal(reviewRecency({ ...current, decisions: [] }), 'none')
})
